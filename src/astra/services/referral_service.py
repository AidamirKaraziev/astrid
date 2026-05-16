from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import Settings, get_settings
from astra.points import crud as points_crud
from astra.points.models import PointsReason
from astra.referrals import crud as referrals_crud
from astra.referrals.models import ReferralStatus
from astra.users.models import User


async def apply_referral_on_start(
    session: AsyncSession,
    invitee: User,
    referral_code: str,
) -> None:
    code_row = await referrals_crud.get_referral_code_by_code(session, referral_code)
    if code_row is None or code_row.user_id == invitee.id:
        return
    await referrals_crud.create_referral(
        session,
        referrer_id=code_row.user_id,
        invitee_id=invitee.id,
    )


async def complete_referral_rewards(
    session: AsyncSession,
    invitee: User,
    settings: Settings | None = None,
) -> None:
    cfg = settings or get_settings()
    referral = await referrals_crud.get_pending_referral_for_invitee(session, invitee.id)
    if referral is None:
        return

    from astra.users import crud as users_crud

    referrer = await users_crud.get_user_by_id(session, referral.referrer_id)
    if referrer is None:
        return

    await points_crud.add_points(
        session,
        referrer,
        cfg.referral_bonus_referrer,
        PointsReason.REFERRAL_BONUS,
        description="Бонус за приглашённого друга",
    )
    await points_crud.add_points(
        session,
        invitee,
        cfg.referral_bonus_invitee,
        PointsReason.REFERRAL_WELCOME,
        description="Добро пожаловать по приглашению",
    )
    referral.status = ReferralStatus.REWARDED
    from datetime import datetime, timezone

    referral.rewarded_at = datetime.now(timezone.utc)
    await session.flush()
