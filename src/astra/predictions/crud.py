from datetime import date
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.predictions.models import Prediction
from astra.predictions.status import PredictionStatus


async def get_prediction_for_date(
    session: AsyncSession,
    user_id: UUID,
    prediction_date: date,
) -> Prediction | None:
    result = await session.execute(
        select(Prediction).where(
            Prediction.user_id == user_id,
            Prediction.prediction_date == prediction_date,
        ),
    )
    return result.scalar_one_or_none()


async def create_prediction(
    session: AsyncSession,
    *,
    user_id: UUID,
    prediction_date: date,
    text: str | None = None,
    astro_context: dict | None = None,
    status: PredictionStatus = PredictionStatus.PENDING,
) -> Prediction:
    prediction = Prediction(
        user_id=user_id,
        prediction_date=prediction_date,
        text=text,
        astro_context=astro_context,
        status=status.value,
    )
    session.add(prediction)
    await session.flush()
    return prediction


async def delete_predictions_for_date(
    session: AsyncSession,
    user_id: UUID,
    prediction_date: date,
) -> int:
    result = await session.execute(
        delete(Prediction).where(
            Prediction.user_id == user_id,
            Prediction.prediction_date == prediction_date,
        ),
    )
    return result.rowcount or 0


async def update_prediction(
    session: AsyncSession,
    prediction: Prediction,
    *,
    text: str | None = None,
    astro_context: dict | None = None,
    status: PredictionStatus | None = None,
) -> Prediction:
    if text is not None:
        prediction.text = text
    if astro_context is not None:
        prediction.astro_context = astro_context
    if status is not None:
        prediction.status = status.value
    await session.flush()
    return prediction


async def upsert_context_draft(
    session: AsyncSession,
    *,
    user_id: UUID,
    prediction_date: date,
    astro_context: dict,
) -> Prediction:
    existing = await get_prediction_for_date(session, user_id, prediction_date)
    if existing is None:
        return await create_prediction(
            session,
            user_id=user_id,
            prediction_date=prediction_date,
            astro_context=astro_context,
            status=PredictionStatus.CONTEXT_READY,
        )
    return await update_prediction(
        session,
        existing,
        astro_context=astro_context,
        status=PredictionStatus.CONTEXT_READY,
    )
