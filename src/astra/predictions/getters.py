from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from astra.predictions import crud
from astra.predictions.schemas import PredictionRead
from astra.services.prediction_service import format_prediction_message
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
    message = format_prediction_message(
        user.profile,
        row.text,
        points=user.points,
        streak=user.streak_current,
    )
    return PredictionRead(
        id=row.id,
        prediction_date=row.prediction_date,
        text=row.text,
        message=message,
        sent_at=row.sent_at,
    )
