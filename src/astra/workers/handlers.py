import asyncio
import logging
from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from astra.messaging.publisher import publish_prediction_send
from astra.services.prediction_pending import clear_prediction_pending
from astra.messaging.schemas import TaskMessage, TaskType
from astra.predictions import crud as predictions_crud
from astra.services.astro_service import refresh_natal_chart_for_profile
from astra.services.prediction_generation import generate_daily_prediction_resilient
from astra.services.prediction_service import format_prediction_for_user, mark_prediction_sent
from astra.users import crud as users_crud
from astra.workers.telegram_send import send_telegram_html

logger = logging.getLogger(__name__)

# Send-задача может прийти на доли секунды раньше commit generate — короткий retry вместо requeue.
_SEND_LOOKUP_RETRIES = 5
_SEND_LOOKUP_DELAY_SEC = 0.1


class PredictionNotReadyError(RuntimeError):
    """Строка предсказания ещё не видна в БД (после retry — requeue в RabbitMQ)."""


async def handle_natal_chart_generate(session: AsyncSession, task: TaskMessage) -> None:
    user = await users_crud.get_user_by_id(session, task.user_id)
    if user is None or user.profile is None:
        logger.warning("Skip natal chart: user or profile missing %s", task.user_id)
        return
    await refresh_natal_chart_for_profile(session, user.profile)
    logger.info("Natal chart stored for user %s", task.user_id)


async def handle_prediction_generate(session: AsyncSession, task: TaskMessage) -> None:
    user = await users_crud.get_user_by_id(session, task.user_id)
    if user is None or user.profile is None:
        logger.warning("Skip prediction generate: user or profile missing %s", task.user_id)
        return

    target = task.prediction_date
    if target is None:
        tz = ZoneInfo(user.profile.timezone)
        from datetime import datetime

        target = datetime.now(tz).date()

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

    # Commit до publish send — иначе send-воркер не видит строку и падает с «not ready yet».
    await session.commit()
    await publish_prediction_send(user.id, target)
    logger.info("Prediction generated for user %s date %s", task.user_id, target)


async def handle_prediction_send(session: AsyncSession, task: TaskMessage) -> None:
    if task.prediction_date is None:
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
        if prediction is not None:
            break
        if attempt + 1 < _SEND_LOOKUP_RETRIES:
            await asyncio.sleep(_SEND_LOOKUP_DELAY_SEC)

    if prediction is None:
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

    message = format_prediction_for_user(prediction, user, user.profile)
    await send_telegram_html(user.telegram_id, message)
    await mark_prediction_sent(session, prediction)
    await clear_prediction_pending(user.id, task.prediction_date)
    logger.info("Prediction sent to telegram_id=%s", user.telegram_id)


async def dispatch_task(session: AsyncSession, task: TaskMessage) -> None:
    if task.type == TaskType.NATAL_CHART_GENERATE:
        await handle_natal_chart_generate(session, task)
    elif task.type == TaskType.PREDICTION_GENERATE:
        await handle_prediction_generate(session, task)
    elif task.type == TaskType.PREDICTION_SEND:
        await handle_prediction_send(session, task)
    else:
        logger.warning("Unknown task type: %s", task.type)
