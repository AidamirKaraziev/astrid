import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from astra.messaging.publisher import (
    publish_compatibility_generate,
    publish_compatibility_send,
    publish_daily_context_build,
    publish_pdf_generate,
    publish_prediction_generate,
    publish_prediction_send,
)
from astra.messaging.schemas import TaskMessage, TaskType
from astra.predictions import crud as predictions_crud
from astra.services.astro_service import (
    build_and_store_daily_context,
    compute_and_store_natal_chart,
)
from astra.services.compatibility_service import (
    build_and_store_synastry,
    deliver_compatibility_report,
    generate_compatibility_llm,
    generate_compatibility_pdf,
)
from astra.services.prediction_generation import generate_daily_prediction_resilient
from astra.services.prediction_pending import clear_prediction_pending
from astra.services.prediction_service import format_prediction_for_user, mark_prediction_sent
from astra.telegram.progress.api import send_chat_action_typing
from astra.telegram.progress import (
    CompatibilityStage,
    PredictionStage,
    clear_progress,
    compatibility_job_key,
    notify_compatibility_stage,
    notify_prediction_stage,
    prediction_job_key,
)
from astra.users import crud as users_crud
from astra.users.models import Profile
from astra.workers.telegram_send import send_prediction_to_telegram

logger = logging.getLogger(__name__)

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
        logger.warning("Skip natal chart: user or profile missing %s", task.user_id)
        return

    target = _target_date(task, user.profile)
    await compute_and_store_natal_chart(session, user, user.profile)
    await session.commit()

    await notify_prediction_stage(
        user.telegram_id,
        user.id,
        target,
        PredictionStage.NATAL_DONE,
    )
    await publish_daily_context_build(user.id, target)
    logger.info("Natal chart stored for user %s date %s", task.user_id, target)


async def handle_daily_context_build(session: AsyncSession, task: TaskMessage) -> None:
    if task.user_id is None:
        return
    user = await users_crud.get_user_by_id(session, task.user_id)
    if user is None or user.profile is None:
        logger.warning("Skip daily context: user or profile missing %s", task.user_id)
        return

    target = _target_date(task, user.profile)
    await build_and_store_daily_context(session, user, user.profile, target)
    await session.commit()

    await notify_prediction_stage(
        user.telegram_id,
        user.id,
        target,
        PredictionStage.CONTEXT_DONE,
    )
    await publish_prediction_generate(user.id, target)
    logger.info("Daily context stored for user %s date %s", task.user_id, target)


async def handle_prediction_generate(session: AsyncSession, task: TaskMessage) -> None:
    if task.user_id is None:
        return
    user = await users_crud.get_user_by_id(session, task.user_id)
    if user is None or user.profile is None:
        logger.warning("Skip prediction generate: user or profile missing %s", task.user_id)
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
        logger.warning(
            "Prediction generation abandoned for user %s date %s",
            task.user_id,
            target,
        )
        return

    await session.commit()
    await publish_prediction_send(user.id, target)
    logger.info("Prediction generated for user %s date %s", task.user_id, target)


async def handle_prediction_send(session: AsyncSession, task: TaskMessage) -> None:
    if task.prediction_date is None or task.user_id is None:
        logger.warning("Skip send: no prediction_date for %s", task.user_id)
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
        logger.warning(
            "Prediction still missing for user %s date %s after %s retries, requeue send",
            user.id,
            task.prediction_date,
            _SEND_LOOKUP_RETRIES,
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
    logger.info("Prediction sent to telegram_id=%s", user.telegram_id)


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
    logger.info("Synastry stored for compatibility report %s", task.report_id)


async def handle_compatibility_generate(session: AsyncSession, task: TaskMessage) -> None:
    if task.report_id is None:
        logger.warning("Skip compatibility LLM: no report_id")
        return

    from astra.compatibility import crud as compatibility_crud

    draft = await compatibility_crud.get_compatibility_report(session, task.report_id)
    if draft is not None:
        user = await users_crud.get_user_by_id(session, draft.owner_user_id)
        if user is not None:
            await send_chat_action_typing(user.telegram_id)

    report = await generate_compatibility_llm(session, task.report_id)
    if report is None:
        logger.warning("Compatibility LLM abandoned for report %s", task.report_id)
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
    logger.info("Compatibility LLM done for report %s", task.report_id)


async def handle_pdf_generate(session: AsyncSession, task: TaskMessage) -> None:
    if task.report_id is None:
        logger.warning("Skip PDF generate: no report_id")
        return

    report = await generate_compatibility_pdf(session, task.report_id)
    if report is None:
        logger.warning("Compatibility PDF abandoned for report %s", task.report_id)
        return

    await session.commit()
    await publish_compatibility_send(report.id)
    logger.info("Compatibility PDF ready for report %s", task.report_id)


async def handle_compatibility_send(session: AsyncSession, task: TaskMessage) -> None:
    if task.report_id is None:
        logger.warning("Skip compatibility send: no report_id")
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
        logger.info("Compatibility report sent %s", task.report_id)


async def dispatch_task(session: AsyncSession, task: TaskMessage) -> None:
    if task.type == TaskType.NATAL_CHART_GENERATE:
        await handle_natal_chart_generate(session, task)
    elif task.type == TaskType.DAILY_CONTEXT_BUILD:
        await handle_daily_context_build(session, task)
    elif task.type == TaskType.PREDICTION_GENERATE:
        await handle_prediction_generate(session, task)
    elif task.type == TaskType.PREDICTION_SEND:
        await handle_prediction_send(session, task)
    elif task.type == TaskType.SYNASTRY_BUILD:
        await handle_synastry_build(session, task)
    elif task.type == TaskType.COMPATIBILITY_GENERATE:
        await handle_compatibility_generate(session, task)
    elif task.type == TaskType.PDF_GENERATE:
        await handle_pdf_generate(session, task)
    elif task.type == TaskType.COMPATIBILITY_SEND:
        await handle_compatibility_send(session, task)
    else:
        logger.warning("Unknown task type: %s", task.type)
