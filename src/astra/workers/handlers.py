import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.observability import Event, get_logger
from astra.messaging.publisher import (
    publish_compatibility_generate,
    publish_compatibility_send,
    publish_daily_context_build,
    publish_day_card_send,
    publish_natal_pdf_generate,
    publish_natal_send,
    publish_pdf_generate,
    publish_prediction_generate,
    publish_prediction_send,
    publish_tarot_reading_generate,
    publish_tarot_reading_send,
)
from astra.messaging.schemas import TaskMessage, TaskType
from astra.predictions import crud as predictions_crud
from astra.services.astro_service import (
    build_and_store_daily_context,
    compute_and_store_natal_chart,
)
from astra.services.natal_report_service import (
    deliver_natal_report,
    generate_natal_llm,
    generate_natal_report_pdf,
)
from astra.services.compatibility_service import (
    build_and_store_synastry,
    deliver_compatibility_report,
    generate_compatibility_llm,
    generate_compatibility_pdf,
)
from astra.services.day_card_service import deliver_day_card
from astra.services.prediction_generation import generate_daily_prediction_resilient
from astra.services.tarot_reading_service import (
    deliver_reading,
    generate_reading_interpretation,
    notify_reading_failed,
)
from astra.services.prediction_pending import clear_prediction_pending
from astra.services.prediction_service import format_prediction_for_user, mark_prediction_sent
from astra.telegram.progress.api import send_chat_action_typing
from astra.telegram.progress import (
    CompatibilityStage,
    NatalStage,
    clear_progress,
    compatibility_job_key,
    natal_job_key,
    notify_compatibility_stage,
    notify_natal_stage,
    prediction_job_key,
)
from astra.users import crud as users_crud
from astra.users.models import Profile
from astra.workers.telegram_send import send_prediction_to_telegram

log = get_logger(__name__)

_SEND_LOOKUP_RETRIES = 5
_SEND_LOOKUP_DELAY_SEC = 0.1


class PredictionNotReadyError(RuntimeError):
    """Строка предсказания ещё не видна в БД (после retry — requeue в RabbitMQ)."""


def _target_date(task: TaskMessage, profile: Profile) -> date:
    if task.prediction_date is not None:
        return task.prediction_date
    return datetime.now(ZoneInfo(profile.timezone)).date()


async def handle_natal_chart_generate(session: AsyncSession, task: TaskMessage) -> None:
    if task.user_id is None:
        return
    user = await users_crud.get_user_by_id(session, task.user_id)
    if user is None or user.profile is None:
        log.warning(Event.TASK_SKIPPED, reason="profile_missing", user_id=task.user_id)
        return

    target = _target_date(task, user.profile)
    await compute_and_store_natal_chart(session, user, user.profile)
    await session.commit()

    # Карта дня приходит рассылкой: этапы пайплайна пользователю не показываем.
    await publish_daily_context_build(user.id, target)
    log.info(Event.PREDICTION_NATAL_STORED, user_id=task.user_id, prediction_date=str(target))


async def handle_daily_context_build(session: AsyncSession, task: TaskMessage) -> None:
    if task.user_id is None:
        return
    user = await users_crud.get_user_by_id(session, task.user_id)
    if user is None or user.profile is None:
        log.warning(Event.TASK_SKIPPED, reason="profile_missing", user_id=task.user_id)
        return

    target = _target_date(task, user.profile)
    await build_and_store_daily_context(session, user, user.profile, target)
    await session.commit()

    # Астро-контекст дня — вход для прогноза по карте; текст прогноза v4.1
    # больше не генерируется (продукт заменён картой дня).
    await publish_day_card_send(user.id, target)
    log.info(Event.PREDICTION_CONTEXT_STORED, user_id=task.user_id, prediction_date=str(target))


async def handle_day_card_send(session: AsyncSession, task: TaskMessage) -> None:
    """Утренняя рассылка карты дня: фото + кнопка «Что это значит для меня»."""
    if task.user_id is None:
        return
    user = await users_crud.get_user_by_id(session, task.user_id)
    if user is None or user.profile is None:
        log.warning(Event.TASK_SKIPPED, reason="profile_missing", user_id=task.user_id)
        return

    target = _target_date(task, user.profile)
    prediction = await predictions_crud.get_prediction_for_date(session, user.id, target)
    if prediction is not None and prediction.sent_at is not None:
        await clear_prediction_pending(user.id, target)
        return  # идемпотентность при requeue

    await clear_progress(user.telegram_id, user.id, prediction_job_key(target))
    await deliver_day_card(session, user, target)
    if prediction is not None:
        await mark_prediction_sent(session, prediction)
    await session.commit()
    await clear_prediction_pending(user.id, target)


async def handle_prediction_generate(session: AsyncSession, task: TaskMessage) -> None:
    if task.user_id is None:
        return
    user = await users_crud.get_user_by_id(session, task.user_id)
    if user is None or user.profile is None:
        log.warning(Event.TASK_SKIPPED, reason="profile_missing", user_id=task.user_id)
        return

    target = _target_date(task, user.profile)
    await send_chat_action_typing(user.telegram_id)
    prediction = await generate_daily_prediction_resilient(
        session,
        user,
        user.profile,
        target=target,
    )
    if prediction is None:
        log.warning(
            Event.PREDICTION_ABANDONED,
            user_id=task.user_id,
            prediction_date=str(target),
        )
        return

    await session.commit()
    await publish_prediction_send(user.id, target)
    log.info(Event.PREDICTION_GENERATED, user_id=task.user_id, prediction_date=str(target))


async def handle_prediction_send(session: AsyncSession, task: TaskMessage) -> None:
    if task.prediction_date is None or task.user_id is None:
        log.warning(Event.TASK_SKIPPED, reason="missing_prediction_date", user_id=task.user_id)
        return

    user = await users_crud.get_user_by_id(session, task.user_id)
    if user is None or user.profile is None:
        return

    prediction = None
    for attempt in range(_SEND_LOOKUP_RETRIES):
        prediction = await predictions_crud.get_prediction_for_date(
            session,
            user.id,
            task.prediction_date,
        )
        if prediction is not None and prediction.text:
            break
        if attempt + 1 < _SEND_LOOKUP_RETRIES:
            await asyncio.sleep(_SEND_LOOKUP_DELAY_SEC)

    if prediction is None or not prediction.text:
        log.warning(
            Event.TASK_SKIPPED,
            reason="prediction_not_ready",
            user_id=user.id,
            prediction_date=str(task.prediction_date),
            retries=_SEND_LOOKUP_RETRIES,
        )
        raise PredictionNotReadyError("Prediction not ready yet")

    if prediction.sent_at is not None:
        await clear_prediction_pending(user.id, task.prediction_date)
        return

    job_key = prediction_job_key(task.prediction_date)
    await clear_progress(user.telegram_id, user.id, job_key)

    message = format_prediction_for_user(prediction, user, user.profile)
    await send_prediction_to_telegram(user.telegram_id, message)
    await mark_prediction_sent(session, prediction)
    await clear_prediction_pending(user.id, task.prediction_date)
    log.info(Event.PREDICTION_SENT, telegram_id=user.telegram_id, user_id=user.id)


async def handle_synastry_build(session: AsyncSession, task: TaskMessage) -> None:
    if task.report_id is None:
        return
    report = await build_and_store_synastry(session, task.report_id)
    if report is None:
        return

    user = await users_crud.get_user_by_id(session, report.owner_user_id)
    if user is None:
        return

    await session.commit()
    await notify_compatibility_stage(
        user.telegram_id,
        user.id,
        report.id,
        CompatibilityStage.SYNASTRY_DONE,
    )
    await publish_compatibility_generate(report.id)
    log.info(Event.COMPATIBILITY_SYNASTRY_STORED, report_id=task.report_id)


async def handle_compatibility_generate(session: AsyncSession, task: TaskMessage) -> None:
    if task.report_id is None:
        log.warning(Event.TASK_SKIPPED, reason="missing_report_id")
        return

    from astra.compatibility import crud as compatibility_crud

    draft = await compatibility_crud.get_compatibility_report(session, task.report_id)
    if draft is not None:
        user = await users_crud.get_user_by_id(session, draft.owner_user_id)
        if user is not None:
            await send_chat_action_typing(user.telegram_id)

    report = await generate_compatibility_llm(session, task.report_id)
    if report is None:
        log.warning(Event.COMPATIBILITY_LLM_ABANDONED, report_id=task.report_id)
        return

    user = await users_crud.get_user_by_id(session, report.owner_user_id)
    if user is None:
        return

    await session.commit()
    await notify_compatibility_stage(
        user.telegram_id,
        user.id,
        report.id,
        CompatibilityStage.LLM_DONE,
    )
    await publish_pdf_generate(report.id)
    log.info(Event.COMPATIBILITY_LLM_DONE, report_id=task.report_id)


async def handle_pdf_generate(session: AsyncSession, task: TaskMessage) -> None:
    if task.report_id is None:
        log.warning(Event.TASK_SKIPPED, reason="missing_report_id")
        return

    report = await generate_compatibility_pdf(session, task.report_id)
    if report is None:
        log.warning(Event.COMPATIBILITY_PDF_ABANDONED, report_id=task.report_id)
        return

    await session.commit()
    await publish_compatibility_send(report.id)
    log.info(Event.COMPATIBILITY_PDF_READY, report_id=task.report_id)


async def handle_compatibility_send(session: AsyncSession, task: TaskMessage) -> None:
    if task.report_id is None:
        log.warning(Event.TASK_SKIPPED, reason="missing_report_id")
        return

    from astra.compatibility import crud as compatibility_crud

    report = await compatibility_crud.get_compatibility_report(session, task.report_id)
    if report is None:
        return

    user = await users_crud.get_user_by_id(session, report.owner_user_id)
    if user is not None and report.sent_at is None:
        job_key = compatibility_job_key(report.id)
        await clear_progress(user.telegram_id, user.id, job_key)

    sent = await deliver_compatibility_report(session, task.report_id)
    if sent:
        log.info(Event.COMPATIBILITY_SENT, report_id=task.report_id)


async def handle_natal_generate(session: AsyncSession, task: TaskMessage) -> None:
    if task.report_id is None:
        log.warning(Event.TASK_SKIPPED, reason="missing_report_id")
        return

    from astra.natal_report import crud as natal_crud

    draft = await natal_crud.get_natal_report(session, task.report_id)
    if draft is not None:
        user = await users_crud.get_user_by_id(session, draft.owner_user_id)
        if user is not None:
            await send_chat_action_typing(user.telegram_id)

    report = await generate_natal_llm(session, task.report_id)
    if report is None:
        log.warning(Event.NATAL_REPORT_LLM_FAILED, report_id=task.report_id, reason="abandoned")
        return

    user = await users_crud.get_user_by_id(session, report.owner_user_id)
    if user is None:
        return

    await session.commit()
    await notify_natal_stage(user.telegram_id, user.id, report.id, NatalStage.LLM_DONE)
    await publish_natal_pdf_generate(report.id)
    log.info(Event.NATAL_REPORT_LLM_DONE, report_id=task.report_id)


async def handle_natal_pdf_generate(session: AsyncSession, task: TaskMessage) -> None:
    if task.report_id is None:
        log.warning(Event.TASK_SKIPPED, reason="missing_report_id")
        return

    report = await generate_natal_report_pdf(session, task.report_id)
    if report is None:
        log.warning(Event.NATAL_REPORT_PDF_FAILED, report_id=task.report_id, reason="abandoned")
        return

    await session.commit()
    await publish_natal_send(report.id)
    log.info(Event.NATAL_REPORT_PDF_READY, report_id=task.report_id)


async def handle_natal_send(session: AsyncSession, task: TaskMessage) -> None:
    if task.report_id is None:
        log.warning(Event.TASK_SKIPPED, reason="missing_report_id")
        return

    from astra.natal_report import crud as natal_crud

    report = await natal_crud.get_natal_report(session, task.report_id)
    if report is None:
        return

    user = await users_crud.get_user_by_id(session, report.owner_user_id)
    if user is not None and report.sent_at is None:
        await clear_progress(user.telegram_id, user.id, natal_job_key(report.id))

    sent = await deliver_natal_report(session, task.report_id)
    if sent:
        log.info(Event.NATAL_REPORT_SENT, report_id=task.report_id)


async def handle_tarot_reading_generate(session: AsyncSession, task: TaskMessage) -> None:
    if task.reading_id is None:
        log.warning(Event.TASK_SKIPPED, reason="missing_reading_id")
        return

    from astra.tarot import models as tarot_crud
    from astra.tarot.enums import ReadingStatus

    draft = await tarot_crud.get_reading(session, task.reading_id)
    if draft is None:
        return
    if draft.status == ReadingStatus.PENDING_PAYMENT:
        # Не должен попадать в очередь до оплаты; страховка от рассинхрона.
        log.warning(Event.TASK_SKIPPED, reason="reading_not_paid", reading_id=draft.id)
        return
    if draft.interpretation and draft.status in (ReadingStatus.TEXT_READY, ReadingStatus.READY):
        await publish_tarot_reading_send(draft.id)  # requeue после рестарта: LLM не повторяем
        return

    user = await users_crud.get_user_by_id(session, draft.user_id)
    if user is not None:
        await send_chat_action_typing(user.telegram_id)

    reading = await generate_reading_interpretation(session, task.reading_id)
    if reading is None:
        from astra.payments.service import refund_reading_payment

        refunded = False
        if user is not None:
            refunded = await refund_reading_payment(session, draft, user.telegram_id)
        await session.commit()  # failed-статус и refund фиксируем вместе
        await notify_reading_failed(session, draft, refunded=refunded)
        return

    await session.commit()
    await publish_tarot_reading_send(reading.id)


async def handle_tarot_reading_send(session: AsyncSession, task: TaskMessage) -> None:
    if task.reading_id is None:
        log.warning(Event.TASK_SKIPPED, reason="missing_reading_id")
        return
    sent = await deliver_reading(session, task.reading_id)
    if sent:
        await session.commit()


async def dispatch_task(session: AsyncSession, task: TaskMessage) -> None:
    if task.type == TaskType.NATAL_CHART_GENERATE:
        await handle_natal_chart_generate(session, task)
    elif task.type == TaskType.DAILY_CONTEXT_BUILD:
        await handle_daily_context_build(session, task)
    elif task.type == TaskType.PREDICTION_GENERATE:
        await handle_prediction_generate(session, task)
    elif task.type == TaskType.PREDICTION_SEND:
        await handle_prediction_send(session, task)
    elif task.type == TaskType.DAY_CARD_SEND:
        await handle_day_card_send(session, task)
    elif task.type == TaskType.SYNASTRY_BUILD:
        await handle_synastry_build(session, task)
    elif task.type == TaskType.COMPATIBILITY_GENERATE:
        await handle_compatibility_generate(session, task)
    elif task.type == TaskType.PDF_GENERATE:
        await handle_pdf_generate(session, task)
    elif task.type == TaskType.COMPATIBILITY_SEND:
        await handle_compatibility_send(session, task)
    elif task.type == TaskType.NATAL_GENERATE:
        await handle_natal_generate(session, task)
    elif task.type == TaskType.NATAL_PDF_GENERATE:
        await handle_natal_pdf_generate(session, task)
    elif task.type == TaskType.NATAL_SEND:
        await handle_natal_send(session, task)
    elif task.type == TaskType.TAROT_READING_GENERATE:
        await handle_tarot_reading_generate(session, task)
    elif task.type == TaskType.TAROT_READING_SEND:
        await handle_tarot_reading_send(session, task)
    else:
        log.warning(Event.TASK_SKIPPED, reason="unknown_task_type", task_type=str(task.type))
