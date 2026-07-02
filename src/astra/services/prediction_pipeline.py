"""Старт и возобновление пайплайна ежедневного предсказания."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from astra.astro import crud as astro_crud
from astra.messaging.publisher import (
    publish_daily_context_build,
    publish_natal_chart,
    publish_prediction_generate,
    publish_prediction_send,
)
from astra.predictions.models import Prediction
from astra.predictions.status import PredictionStatus


async def enqueue_prediction_pipeline(
    session: AsyncSession,
    user_id: UUID,
    target: date,
) -> None:
    """Первая задача: натал (если нет в БД) или расчёт транзитов дня."""
    natal = await astro_crud.get_natal_chart(session, user_id)
    if natal is None:
        await publish_natal_chart(user_id, target)
        return
    await publish_daily_context_build(user_id, target)


async def resume_prediction_pipeline(
    session: AsyncSession,
    user_id: UUID,
    target: date,
    prediction: Prediction | None,
) -> None:
    """Продолжить пайплайн с нужного этапа."""
    if prediction is None:
        await enqueue_prediction_pipeline(session, user_id, target)
        return

    status = PredictionStatus(prediction.status)
    if status == PredictionStatus.CONTEXT_READY:
        await publish_prediction_generate(user_id, target)
        return
    if status == PredictionStatus.TEXT_READY:
        await publish_prediction_send(user_id, target)
        return

    await enqueue_prediction_pipeline(session, user_id, target)
