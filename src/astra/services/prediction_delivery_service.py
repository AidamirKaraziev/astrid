"""Доставка предсказания в Telegram после генерации."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from astra.core.observability import Event, get_logger
from astra.db.session import get_session_factory
from astra.services.prediction_pending import (
    clear_prediction_pending,
    try_mark_prediction_pending,
)
from astra.services.prediction_pipeline import enqueue_prediction_pipeline
from astra.users import crud as users_crud

log = get_logger(__name__)


async def enqueue_first_prediction_after_registration(user_id: UUID) -> None:
    """Запустить пайплайн первого предсказания после регистрации (без staged UX)."""
    target = date.today()
    session_factory = get_session_factory()

    if not await try_mark_prediction_pending(user_id, target):
        log.info(Event.PREDICTION_DEDUP_HIT, user_id=user_id, prediction_date=str(target))
        return

    try:
        async with session_factory() as session:
            await enqueue_prediction_pipeline(session, user_id, target)
            await session.commit()
    except Exception:
        await clear_prediction_pending(user_id, target)
        raise

    log.info(Event.PREDICTION_QUEUED, user_id=user_id, prediction_date=str(target))
