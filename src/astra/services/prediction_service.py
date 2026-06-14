from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from astra.predictions import crud as predictions_crud
from astra.predictions.models import Prediction
from astra.services.prediction_generation import generate_daily_prediction_resilient
from astra.services.prediction_pending import (
    clear_prediction_pending,
    is_prediction_pending,
    try_mark_prediction_pending,
)
from astra.users.models import Profile, User

PREDICTION_IN_PROGRESS_TEXT = (
    "Почти готово ✨\n"
    "Твоё предсказание уже готовится — пришлю сюда через минутку."
)


class PredictionRequestStatus(StrEnum):
    READY = "ready"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PredictionRequestOutcome:
    status: PredictionRequestStatus
    prediction: Prediction | None = None


def format_prediction_message(
    profile: Profile,
    body: str,
    *,
    points: int = 0,
    streak: int = 0,
) -> str:
    """Текст предсказания для отправки в Telegram (без обёртки)."""
    del profile, points, streak
    return body.strip()


def format_prediction_for_user(
    prediction: Prediction,
    user: User,
    profile: Profile,
) -> str:
    del user, profile
    return prediction.text.strip()


def _today_for_profile(profile: Profile, today: date | None) -> date:
    if today is not None:
        return today
    return datetime.now(ZoneInfo(profile.timezone)).date()


async def _enqueue_generate(user_id, target: date) -> None:  # noqa: ANN001
    from astra.messaging.publisher import publish_prediction_generate

    await publish_prediction_generate(user_id, target)


async def _enqueue_send(user_id, target: date) -> None:  # noqa: ANN001
    from astra.messaging.publisher import publish_prediction_send

    await publish_prediction_send(user_id, target)


async def request_today_prediction(
    session: AsyncSession,
    user: User,
    profile: Profile,
    today: date | None = None,
    *,
    allow_async: bool = False,
) -> PredictionRequestOutcome:
    """Запросить предсказание на день: без дублей в RabbitMQ при повторных нажатиях."""
    from astra.core.config import get_settings

    target = _today_for_profile(profile, today)
    existing = await predictions_crud.get_prediction_for_date(session, user.id, target)

    if existing is not None:
        if existing.sent_at is not None:
            return PredictionRequestOutcome(
                status=PredictionRequestStatus.READY,
                prediction=existing,
            )
        if await is_prediction_pending(user.id, target):
            return PredictionRequestOutcome(status=PredictionRequestStatus.IN_PROGRESS)
        settings = get_settings()
        if allow_async and settings.rabbitmq_enabled:
            if not await try_mark_prediction_pending(user.id, target):
                return PredictionRequestOutcome(status=PredictionRequestStatus.IN_PROGRESS)
            try:
                await _enqueue_send(user.id, target)
            except Exception:
                await clear_prediction_pending(user.id, target)
                raise
            return PredictionRequestOutcome(status=PredictionRequestStatus.QUEUED)
        return PredictionRequestOutcome(
            status=PredictionRequestStatus.READY,
            prediction=existing,
        )

    settings = get_settings()
    if allow_async and settings.rabbitmq_enabled:
        if not await try_mark_prediction_pending(user.id, target):
            return PredictionRequestOutcome(status=PredictionRequestStatus.IN_PROGRESS)
        try:
            await _enqueue_generate(user.id, target)
        except Exception:
            await clear_prediction_pending(user.id, target)
            raise
        return PredictionRequestOutcome(status=PredictionRequestStatus.QUEUED)

    prediction = await generate_daily_prediction_resilient(session, user, profile, target=target)
    if prediction is None:
        return PredictionRequestOutcome(status=PredictionRequestStatus.FAILED)
    return PredictionRequestOutcome(
        status=PredictionRequestStatus.READY,
        prediction=prediction,
    )


async def get_or_create_today_prediction(
    session: AsyncSession,
    user: User,
    profile: Profile,
    today: date | None = None,
    *,
    allow_async: bool = False,
) -> Prediction | None:
    outcome = await request_today_prediction(
        session,
        user,
        profile,
        today,
        allow_async=allow_async,
    )
    if outcome.status == PredictionRequestStatus.READY:
        return outcome.prediction
    return None


async def mark_prediction_sent(session: AsyncSession, prediction: Prediction) -> None:
    prediction.sent_at = datetime.now(timezone.utc)
    await session.flush()
