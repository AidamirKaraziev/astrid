from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import Settings, get_settings
from astra.points import crud as points_crud
from astra.points.models import PointsReason
from astra.referrals import crud
from astra.referrals.schemas import ReferralStatsRead


async def get_referral_stats(
    session: AsyncSession,
    user_id: UUID,
    settings: Settings | None = None,
) -> ReferralStatsRead:
    cfg = settings or get_settings()
    code_row = await crud.get_or_create_referral_code(session, user_id)
    invited = await crud.count_referrals(session, user_id)
    earned = await points_crud.sum_points_by_reason(
        session,
        user_id,
        PointsReason.REFERRAL_BONUS,
    )
    bot_username = cfg.telegram_bot_username.lstrip("@")
    link = f"https://t.me/{bot_username}?start=ref_{code_row.code}"
    return ReferralStatsRead(
        code=code_row.code,
        referral_link=link,
        invited_count=invited,
        points_earned=earned,
    )
