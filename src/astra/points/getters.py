from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from astra.points.schemas import PointsBalanceRead
from astra.users import crud


async def get_points_balance(session: AsyncSession, user_id: UUID) -> PointsBalanceRead | None:
    user = await crud.get_user_by_id(session, user_id)
    if user is None:
        return None
    return PointsBalanceRead(
        points=user.points,
        streak_current=user.streak_current,
        streak_best=user.streak_best,
    )
