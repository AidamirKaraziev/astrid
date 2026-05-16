from datetime import date
from uuid import UUID

from sqlalchemy import select
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
    accuracy_percent: int,
) -> Prediction:
    prediction = Prediction(
        user_id=user_id,
        prediction_date=prediction_date,
        text=text,
        accuracy_percent=accuracy_percent,
    )
    session.add(prediction)
    await session.flush()
    return prediction
