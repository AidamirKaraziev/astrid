from datetime import date
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.predictions.models import Prediction


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
    text: str,
    astro_context: dict | None = None,
) -> Prediction:
    prediction = Prediction(
        user_id=user_id,
        prediction_date=prediction_date,
        text=text,
        astro_context=astro_context,
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
) -> Prediction:
    if text is not None:
        prediction.text = text
    if astro_context is not None:
        prediction.astro_context = astro_context
    await session.flush()
    return prediction
