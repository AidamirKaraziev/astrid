"""Устойчивая генерация предсказания: ретраи, уведомление о задержке, Sentry."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import Settings, get_settings
from astra.core.prediction_errors import LlmGenerationError, report_prediction_generation_failure
from astra.predictions.models import Prediction
from astra.services.astro_service import generate_daily_prediction
from astra.services.prediction_delayed_notify import (
    maybe_send_delayed_notification,
    send_final_failure_notification,
)
from astra.services.prediction_pending import clear_prediction_pending
from astra.users.models import Profile, User

logger = logging.getLogger(__name__)

PREDICTION_DELAYED_NOTIFY_SEC = 120
PREDICTION_MAX_ATTEMPTS = 15
_BACKOFF_SEC = (5, 15, 30, 45, 60)


def _backoff_seconds(attempt: int) -> float:
    index = min(attempt - 1, len(_BACKOFF_SEC) - 1)
    return float(_BACKOFF_SEC[index])


async def generate_daily_prediction_resilient(
    session: AsyncSession,
    user: User,
    profile: Profile,
    target: date,
    settings: Settings | None = None,
) -> Prediction | None:
    """Генерировать предсказание с ретраями; None — исчерпаны попытки, юзер уведомлён."""
    cfg = settings or get_settings()
    started = time.monotonic()
    last_reason = "unknown"

    for attempt in range(1, PREDICTION_MAX_ATTEMPTS + 1):
        elapsed = time.monotonic() - started
        if elapsed >= PREDICTION_DELAYED_NOTIFY_SEC:
            await maybe_send_delayed_notification(user.id, user.telegram_id, target)

        try:
            prediction = await generate_daily_prediction(
                session,
                user,
                profile,
                target=target,
                settings=cfg,
            )
            if attempt > 1:
                logger.info(
                    "prediction generated after %s attempts for user %s date %s",
                    attempt,
                    user.id,
                    target,
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
                logger.error(
                    "prediction generation failed after %s attempts for user %s date %s: %s",
                    attempt,
                    user.id,
                    target,
                    exc,
                )
                await send_final_failure_notification(user.telegram_id)
                await clear_prediction_pending(user.id, target)
                return None

            logger.warning(
                "prediction attempt %s failed for user %s date %s: %s; retry in %ss",
                attempt,
                user.id,
                target,
                exc,
                _backoff_seconds(attempt),
            )
            await asyncio.sleep(_backoff_seconds(attempt))

    return None
