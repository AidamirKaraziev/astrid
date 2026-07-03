"""Устойчивая генерация предсказания: ретраи, уведомление о задержке, Sentry."""

from __future__ import annotations

import asyncio
import time
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger
from astra.core.prediction_errors import LlmGenerationError, report_prediction_generation_failure
from astra.predictions import crud as predictions_crud
from astra.predictions.models import Prediction
from astra.predictions.status import PredictionStatus
from astra.services.astro_service import generate_prediction_text_only
from astra.services.prediction_delayed_notify import (
    maybe_send_delayed_notification,
    send_final_failure_notification,
)
from astra.services.prediction_pending import clear_prediction_pending
from astra.users.models import Profile, User

log = get_logger(__name__)

PREDICTION_DELAYED_NOTIFY_SEC = 120
PREDICTION_MAX_ATTEMPTS = 15
_BACKOFF_SEC = (5, 15, 30, 45, 60)


def _backoff_seconds(attempt: int) -> float:
    index = min(attempt - 1, len(_BACKOFF_SEC) - 1)
    return float(_BACKOFF_SEC[index])


async def _mark_prediction_failed(
    session: AsyncSession,
    user_id,
    target: date,
) -> None:  # noqa: ANN001
    prediction = await predictions_crud.get_prediction_for_date(session, user_id, target)
    if prediction is not None:
        await predictions_crud.update_prediction(
            session,
            prediction,
            status=PredictionStatus.FAILED,
        )


async def generate_daily_prediction_resilient(
    session: AsyncSession,
    user: User,
    profile: Profile,
    target: date,
    settings: Settings | None = None,
) -> Prediction | None:
    """Сгенерировать текст предсказания (LLM) с ретраями; None — исчерпаны попытки."""
    cfg = settings or get_settings()
    started = time.monotonic()
    last_reason = "unknown"

    for attempt in range(1, PREDICTION_MAX_ATTEMPTS + 1):
        elapsed = time.monotonic() - started
        if elapsed >= PREDICTION_DELAYED_NOTIFY_SEC:
            await maybe_send_delayed_notification(user.id, user.telegram_id, target)

        try:
            prediction = await generate_prediction_text_only(
                session,
                user,
                profile,
                target=target,
                settings=cfg,
            )
            if attempt > 1:
                log.info(
                    Event.PREDICTION_GENERATED,
                    user_id=user.id,
                    prediction_date=str(target),
                    attempts=attempt,
                )
            return prediction
        except LlmGenerationError as exc:
            last_reason = exc.reason
            elapsed = time.monotonic() - started
            is_final = attempt >= PREDICTION_MAX_ATTEMPTS
            report_prediction_generation_failure(
                user_id=user.id,
                prediction_date=target,
                reason=last_reason,
                attempts=attempt,
                elapsed_sec=elapsed,
                final=is_final,
            )
            if is_final:
                log.error(
                    Event.PREDICTION_GENERATION_FAILED,
                    user_id=user.id,
                    prediction_date=str(target),
                    attempts=attempt,
                    reason=last_reason,
                )
                await send_final_failure_notification(user.telegram_id)
                await _mark_prediction_failed(session, user.id, target)
                await clear_prediction_pending(user.id, target)
                return None

            log.warning(
                Event.PREDICTION_RETRY,
                user_id=user.id,
                prediction_date=str(target),
                attempt=attempt,
                reason=last_reason,
                backoff_sec=_backoff_seconds(attempt),
            )
            await asyncio.sleep(_backoff_seconds(attempt))

    return None
