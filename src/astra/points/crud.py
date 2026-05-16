from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.points.models import PointsLedger, PointsReason
from astra.users.models import User


async def add_points(
    session: AsyncSession,
    user: User,
    delta: int,
    reason: PointsReason,
    description: str | None = None,
) -> PointsLedger:
    entry = PointsLedger(
        user_id=user.id,
        delta=delta,
        reason=reason,
        description=description,
    )
    user.points += delta
    session.add(entry)
    await session.flush()
    return entry


async def sum_points_by_reason(
    session: AsyncSession,
    user_id: UUID,
    reason: PointsReason,
) -> int:
    result = await session.execute(
        select(func.coalesce(func.sum(PointsLedger.delta), 0)).where(
            PointsLedger.user_id == user_id,
            PointsLedger.reason == reason,
        ),
    )
    return int(result.scalar_one())
