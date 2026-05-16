from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import Settings, get_settings
from astra.points import crud as points_crud
from astra.points.models import PointsReason
from astra.users.models import User


async def register_daily_activity(
    session: AsyncSession,
    user: User,
    activity_date: date | None = None,
    settings: Settings | None = None,
) -> tuple[int, int]:
    """Award daily points and update streak. Returns (points_awarded, new_streak)."""
    cfg = settings or get_settings()
    today = activity_date or date.today()

    if user.last_active_date == today:
        return 0, user.streak_current

    previous = user.last_active_date
    user.last_active_date = today

    if previous == today - timedelta(days=1):
        user.streak_current += 1
    else:
        user.streak_current = 1

    user.streak_best = max(user.streak_best, user.streak_current)
    await points_crud.add_points(
        session,
        user,
        cfg.points_daily_visit,
        PointsReason.DAILY_VISIT,
        description="Ежедневный визит",
    )
    return cfg.points_daily_visit, user.streak_current
