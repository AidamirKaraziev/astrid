from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from astra.predictions import crud
from astra.predictions.schemas import PredictionRead
from astra.users import crud as users_crud


async def get_today_prediction(
    session: AsyncSession,
    user_id: UUID,
    today: date | None = None,
) -> PredictionRead | None:
    target = today or date.today()
    row = await crud.get_prediction_for_date(session, user_id, target)
    if row is None:
        return None
    user = await users_crud.get_user_by_id(session, user_id)
    if user is None or user.profile is None:
        return None
    return PredictionRead(
        id=row.id,
        prediction_date=row.prediction_date,
        text=row.text,
        message=row.text.strip(),
        sent_at=row.sent_at,
    )
