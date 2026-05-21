import logging
from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from astra.messaging.publisher import publish_prediction_generate, publish_prediction_send
from astra.messaging.schemas import TaskMessage, TaskType
from astra.predictions import crud as predictions_crud
from astra.services.astro_service import (
    generate_daily_prediction,
    refresh_natal_chart_for_profile,
)
from astra.services.prediction_service import format_prediction_for_user, mark_prediction_sent
from astra.users import crud as users_crud
from astra.workers.telegram_send import send_telegram_html

logger = logging.getLogger(__name__)


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

    await generate_daily_prediction(session, user, user.profile, target=target)
    await publish_prediction_send(user.id, target)
    logger.info("Prediction generated for user %s date %s", task.user_id, target)


async def handle_prediction_send(session: AsyncSession, task: TaskMessage) -> None:
    if task.prediction_date is None:
        logger.warning("Skip send: no prediction_date for %s", task.user_id)
        return

    user = await users_crud.get_user_by_id(session, task.user_id)
    if user is None or user.profile is None:
        return

    prediction = await predictions_crud.get_prediction_for_date(
        session,
        user.id,
        task.prediction_date,
    )
    if prediction is None:
        await publish_prediction_generate(user.id, task.prediction_date)
        raise RuntimeError("Prediction not ready yet")

    if prediction.sent_at is not None:
        return

    message = format_prediction_for_user(prediction, user, user.profile)
    await send_telegram_html(user.telegram_id, message)
    await mark_prediction_sent(session, prediction)
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
