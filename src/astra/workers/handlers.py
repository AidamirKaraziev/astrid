import asyncio
from datetime import date, datetime
from uuid import UUID
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
from astra.compatibility.enums import ReportStatus
from astra.broadcasts import service as broadcast_service
from astra.broadcasts.keyboards import broadcast_keyboard
from astra.broadcasts.models import Broadcast
from astra.messaging.schemas import TaskMessage, TaskType
from astra.predictions import crud as predictions_crud
from astra.predictions.status import PredictionStatus
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
from astra.services.prediction_delayed_notify import send_final_failure_notification
from astra.services.prediction_generation import (
    generate_daily_prediction_resilient,
    mark_prediction_failed,
)
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
from astra.workers.telegram_send import send_prediction_to_telegram, send_telegram_html

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
        await _abandon_prediction(session, user.id, user.telegram_id, target)
        return

    await session.commit()
    await publish_prediction_send(user.id, target)
    log.info(Event.PREDICTION_GENERATED, user_id=task.user_id, prediction_date=str(target))


async def _abandon_prediction(
    session: AsyncSession,
    user_id: UUID,
    telegram_id: int,
    target: date,
) -> None:
    """Предсказание не собралось: одно сообщение человеку, failed-статус, pending снят."""
    await send_final_failure_notification(telegram_id)
    await mark_prediction_failed(session, user_id, target)
    await session.commit()
    await clear_prediction_pending(user_id, target)


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


async def _notify_failure_if_failed(
    session: AsyncSession,
    report_id: UUID,
    *,
    owner_of: str,
) -> None:
    """Единая точка «разбор упал → человек узнал» для натала и совместимости.

    Вызывается воркером, когда сервис вернул ``None`` (или доставка не удалась):
    любой путь падения внутри сервиса покрыт автоматически. Если отчёта или
    владельца нет, сообщать некому.
    """
    if owner_of == "natal":
        from astra.natal_report import crud as natal_crud
        from astra.services.natal_failure_notify import send_natal_failure_notification

        natal_report = await natal_crud.get_natal_report(session, report_id)
        owner_id = natal_report.owner_user_id if natal_report is not None else None
        send = send_natal_failure_notification
    else:
        from astra.compatibility import crud as compatibility_crud
        from astra.services.compatibility_failure_notify import (
            send_compatibility_failure_notification,
        )

        compat_report = await compatibility_crud.get_compatibility_report(session, report_id)
        owner_id = compat_report.owner_user_id if compat_report is not None else None
        send = send_compatibility_failure_notification
    if owner_id is None:
        return
    user = await users_crud.get_user_by_id(session, owner_id)
    if user is not None:
        await send(user.telegram_id)


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
        await _notify_failure_if_failed(session, task.report_id, owner_of="compatibility")
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
        await _notify_failure_if_failed(session, task.report_id, owner_of="compatibility")
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
    elif report.status == ReportStatus.FAILED:
        # доставка пометила разбор failed (pdf_missing)
        await _notify_failure_if_failed(session, task.report_id, owner_of="compatibility")


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
        await _notify_failure_if_failed(session, task.report_id, owner_of="natal")
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
        await _notify_failure_if_failed(session, task.report_id, owner_of="natal")
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


async def handle_ask_answer_generate(session: AsyncSession, task: TaskMessage) -> None:
    """Разбор ответа «Спроси Астрид»: числа уже в БД, пишем текст и шлём."""
    if task.reading_id is None:
        log.warning(Event.TASK_SKIPPED, reason="missing_reading_id")
        return

    from astra.ask import models as ask_crud
    from astra.ask.enums import AskStatus
    from astra.services.ask_service import (
        deliver_ask_answer,
        generate_ask_answer,
        notify_ask_failed,
        refund_ask_payment,
    )

    draft = await ask_crud.get_reading(session, task.reading_id)
    if draft is None:
        return
    if draft.status == AskStatus.PENDING_PAYMENT:
        log.warning(Event.TASK_SKIPPED, reason="ask_not_paid", reading_id=draft.id)
        return

    user = await users_crud.get_user_by_id(session, draft.user_id)
    if user is not None:
        await send_chat_action_typing(user.telegram_id)

    reading = await generate_ask_answer(session, task.reading_id)
    if reading is None:
        refunded = False
        if user is not None:
            refunded = await refund_ask_payment(session, draft, user.telegram_id)
        await session.commit()  # failed-статус и refund фиксируем вместе
        await notify_ask_failed(session, draft, refunded=refunded)
        return

    await session.commit()
    if await deliver_ask_answer(session, reading):
        await session.commit()


async def handle_broadcast_send(session: AsyncSession, task: TaskMessage) -> None:
    """Разослать подготовленную рассылку.

    Панель уже зафиксировала получателей строками, поэтому воркер просто идёт по
    ним и шлёт. Ошибка одного сообщения не рвёт рассылку: заблокировавший бота
    помечается и пропускается, сетевая осечка остаётся «недошедшей» и повторяется
    кнопкой из истории.
    """
    if task.report_id is None:
        return

    broadcast = await session.get(Broadcast, task.report_id)
    if broadcast is None:
        log.warning("broadcast.missing", broadcast_id=task.report_id)
        return

    markup = broadcast_keyboard(broadcast.buttons)

    async def sender(person, text: str) -> None:
        await send_telegram_html(
            person.telegram_id,
            text,
            reply_markup=markup,
            keyboard_zone=None,
        )

    progress = await broadcast_service.send_all(session, broadcast, sender)
    await session.commit()
    log.info(
        "broadcast.sent",
        broadcast_id=broadcast.id,
        sent=progress.sent,
        blocked=progress.blocked,
        failed=progress.failed,
    )


_NATAL_DEAD = frozenset({TaskType.NATAL_GENERATE, TaskType.NATAL_PDF_GENERATE, TaskType.NATAL_SEND})
_COMPATIBILITY_DEAD = frozenset(
    {
        TaskType.SYNASTRY_BUILD,
        TaskType.COMPATIBILITY_GENERATE,
        TaskType.PDF_GENERATE,
        TaskType.COMPATIBILITY_SEND,
    },
)
_PREDICTION_DEAD = frozenset(
    {TaskType.PREDICTION_GENERATE, TaskType.PREDICTION_SEND, TaskType.DAY_CARD_SEND},
)


async def _dead_tarot(session: AsyncSession, task: TaskMessage) -> None:
    from astra.payments.service import refund_reading_payment
    from astra.tarot import models as tarot_crud
    from astra.tarot.enums import ReadingStatus

    if task.reading_id is None:
        return
    reading = await tarot_crud.get_reading(session, task.reading_id)
    if reading is None or reading.sent_at is not None:
        return  # нет расклада или уже доставлен
    if reading.status == ReadingStatus.PENDING_PAYMENT:
        return  # не оплачен: возвращать нечего
    user = await users_crud.get_user_by_id(session, reading.user_id)
    refunded = False
    if user is not None:
        refunded = await refund_reading_payment(session, reading, user.telegram_id)
    reading.status = ReadingStatus.FAILED
    await session.commit()
    await notify_reading_failed(session, reading, refunded=refunded)


async def _dead_ask(session: AsyncSession, task: TaskMessage) -> None:
    from astra.ask import models as ask_crud
    from astra.ask.enums import AskStatus
    from astra.services.ask_service import notify_ask_failed, refund_ask_payment

    if task.reading_id is None:
        return
    reading = await ask_crud.get_reading(session, task.reading_id)
    if reading is None or reading.status in (AskStatus.READY, AskStatus.PENDING_PAYMENT):
        return  # доставлен или не оплачен
    if reading.refunded:
        return  # уже возвращено и сообщено: второй раз не трогаем
    user = await users_crud.get_user_by_id(session, reading.user_id)
    refunded = False
    if user is not None:
        refunded = await refund_ask_payment(session, reading, user.telegram_id)
    if reading.status != AskStatus.FAILED:
        await ask_crud.mark_failed(session, reading, "task_dead")
    await session.commit()
    await notify_ask_failed(session, reading, refunded=refunded)


async def _dead_report(session: AsyncSession, task: TaskMessage, *, owner_of: str) -> None:
    if task.report_id is None:
        return
    if owner_of == "natal":
        from astra.natal_report import crud as natal_crud
        from astra.natal_report.enums import NatalReportStatus

        natal = await natal_crud.get_natal_report(session, task.report_id)
        if natal is None or natal.sent_at is not None or natal.status == NatalReportStatus.FAILED:
            return
        await natal_crud.mark_natal_failed(session, natal, "task_dead")
    else:
        from astra.compatibility import crud as compatibility_crud

        compat = await compatibility_crud.get_compatibility_report(session, task.report_id)
        if compat is None or compat.sent_at is not None or compat.status == ReportStatus.FAILED:
            return
        await compatibility_crud.mark_report_failed(session, compat, "task_dead")
    await session.commit()
    await _notify_failure_if_failed(session, task.report_id, owner_of=owner_of)


async def _dead_prediction(session: AsyncSession, task: TaskMessage) -> None:
    if task.user_id is None:
        return
    user = await users_crud.get_user_by_id(session, task.user_id)
    if user is None or user.profile is None:
        return
    target = _target_date(task, user.profile)
    prediction = await predictions_crud.get_prediction_for_date(session, user.id, target)
    if prediction is not None and (
        prediction.sent_at is not None or prediction.status == PredictionStatus.FAILED
    ):
        return  # уже отправлено или уже обработано как сбой
    await _abandon_prediction(session, user.id, user.telegram_id, target)


async def handle_task_dead(session: AsyncSession, task: TaskMessage) -> None:
    """Задача исчерпала попытки: вернуть деньги и сказать человеку. Никогда не бросает."""
    try:
        if task.type in (TaskType.TAROT_READING_GENERATE, TaskType.TAROT_READING_SEND):
            await _dead_tarot(session, task)
        elif task.type == TaskType.ASK_ANSWER_GENERATE:
            await _dead_ask(session, task)
        elif task.type in _NATAL_DEAD:
            await _dead_report(session, task, owner_of="natal")
        elif task.type in _COMPATIBILITY_DEAD:
            await _dead_report(session, task, owner_of="compatibility")
        elif task.type in _PREDICTION_DEAD:
            await _dead_prediction(session, task)
        # BROADCAST_SEND, NATAL_CHART_GENERATE, DAILY_CONTEXT_BUILD: человеку сказать нечего.
        log.error(Event.TASK_FAILED, task_type=str(task.type), reason="attempts_exhausted")
    except Exception:
        log.exception(Event.TASK_FAILED, task_type=str(task.type), reason="task_dead_handler_failed")


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
    elif task.type == TaskType.BROADCAST_SEND:
        await handle_broadcast_send(session, task)
    elif task.type == TaskType.ASK_ANSWER_GENERATE:
        await handle_ask_answer_generate(session, task)
    else:
        log.warning(Event.TASK_SKIPPED, reason="unknown_task_type", task_type=str(task.type))
