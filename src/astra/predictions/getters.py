from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from astra.predictions import crud
from astra.predictions.schemas import PredictionRead


async def get_today_prediction(
    session: AsyncSession,
    user_id: UUID,
    today: date | None = None,
) -> PredictionRead | None:
    target = today or date.today()
    row = await crud.get_prediction_for_date(session, user_id, target)
    if row is None:
        return None
    return PredictionRead.model_validate(row)
