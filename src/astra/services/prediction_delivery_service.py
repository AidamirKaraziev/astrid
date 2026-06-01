"""Доставка предсказания в Telegram после генерации."""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from uuid import UUID

from astra.core.config import get_settings
from astra.db.session import get_session_factory
from astra.messaging.publisher import publish_prediction_generate
from astra.predictions import crud as predictions_crud
from astra.predictions.models import Prediction
from astra.services.astro_service import generate_daily_prediction
from astra.services.prediction_service import format_prediction_for_user, mark_prediction_sent
from astra.users import crud as users_crud
from astra.workers.telegram_send import send_telegram_html

logger = logging.getLogger(__name__)


async def deliver_prediction_for_date(user_id: UUID, prediction_date: date) -> None:
    """Сгенерировать (если нет) и отправить предсказание пользователю."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await users_crud.get_user_by_id(session, user_id)
        if user is None or user.profile is None:
            logger.warning("deliver_prediction: user or profile missing %s", user_id)
            return

        prediction = await predictions_crud.get_prediction_for_date(
            session,
            user.id,
            prediction_date,
        )
        if prediction is None:
            prediction = await generate_daily_prediction(
                session,
                user,
                user.profile,
                target=prediction_date,
            )

        text = format_prediction_for_user(prediction, user, user.profile)
        telegram_id = user.telegram_id
        prediction_id = prediction.id
        await session.commit()

    try:
        await send_telegram_html(telegram_id, text)
    except Exception:
        logger.exception("failed to send prediction to telegram_id=%s", telegram_id)
        return

    async with session_factory() as session:
        prediction = await session.get(Prediction, prediction_id)
        if prediction is not None and prediction.sent_at is None:
            await mark_prediction_sent(session, prediction)
            await session.commit()


async def enqueue_first_prediction_after_registration(user_id: UUID) -> None:
    """Запустить генерацию и доставку первого предсказания после регистрации."""
    target = date.today()
    settings = get_settings()

    if settings.rabbitmq_enabled:
        await publish_prediction_generate(user_id, target)
        logger.info("queued first prediction via RabbitMQ for user %s", user_id)
        return

    def _log_task_error(done: asyncio.Task[None]) -> None:
        if exc := done.exception():
            logger.error("first prediction task failed for user %s", user_id, exc_info=exc)

    task = asyncio.create_task(
        deliver_prediction_for_date(user_id, target),
        name=f"first-prediction-{user_id}",
    )
    task.add_done_callback(_log_task_error)
    logger.info("started inline first prediction task for user %s", user_id)
