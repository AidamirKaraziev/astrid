from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from astra.predictions import crud as predictions_crud
from astra.predictions.models import Prediction
from astra.predictions.status import PredictionStatus
from astra.services.prediction_pending import (
    clear_prediction_pending,
    is_prediction_pending,
    try_mark_prediction_pending,
)
from astra.services.prediction_pipeline import (
    enqueue_prediction_pipeline,
    resume_prediction_pipeline,
)
from astra.users.models import Profile, User


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
    return (prediction.text or "").strip()


def _today_for_profile(profile: Profile, today: date | None) -> date:
    if today is not None:
        return today
    return datetime.now(ZoneInfo(profile.timezone)).date()


async def _enqueue_pipeline(
    session: AsyncSession,
    user_id,
    target: date,
    prediction: Prediction | None,
) -> None:  # noqa: ANN001
    if prediction is None:
        await enqueue_prediction_pipeline(session, user_id, target)
        return
    await resume_prediction_pipeline(session, user_id, target, prediction)


async def request_today_prediction(
    session: AsyncSession,
    user: User,
    profile: Profile,
    today: date | None = None,
) -> PredictionRequestOutcome:
    """Запросить предсказание на день через RabbitMQ (без дублей при повторных нажатиях)."""
    target = _today_for_profile(profile, today)
    existing = await predictions_crud.get_prediction_for_date(session, user.id, target)

    if existing is not None:
        if existing.sent_at is not None or existing.status == PredictionStatus.SENT.value:
            return PredictionRequestOutcome(
                status=PredictionRequestStatus.READY,
                prediction=existing,
            )
        if await is_prediction_pending(user.id, target):
            return PredictionRequestOutcome(status=PredictionRequestStatus.IN_PROGRESS)
        if not await try_mark_prediction_pending(user.id, target):
            return PredictionRequestOutcome(status=PredictionRequestStatus.IN_PROGRESS)
        try:
            await _enqueue_pipeline(session, user.id, target, existing)
        except Exception:
            await clear_prediction_pending(user.id, target)
            raise
        return PredictionRequestOutcome(status=PredictionRequestStatus.QUEUED)

    if not await try_mark_prediction_pending(user.id, target):
        return PredictionRequestOutcome(status=PredictionRequestStatus.IN_PROGRESS)
    try:
        await _enqueue_pipeline(session, user.id, target, None)
    except Exception:
        await clear_prediction_pending(user.id, target)
        raise
    return PredictionRequestOutcome(status=PredictionRequestStatus.QUEUED)


async def get_or_create_today_prediction(
    session: AsyncSession,
    user: User,
    profile: Profile,
    today: date | None = None,
) -> Prediction | None:
    outcome = await request_today_prediction(session, user, profile, today)
    if outcome.status == PredictionRequestStatus.READY:
        return outcome.prediction
    return None


async def mark_prediction_sent(session: AsyncSession, prediction: Prediction) -> None:
    prediction.sent_at = datetime.now(timezone.utc)
    prediction.status = PredictionStatus.SENT.value
    await session.flush()
