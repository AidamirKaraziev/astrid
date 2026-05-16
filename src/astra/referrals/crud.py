import secrets
import string
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.referrals.models import Referral, ReferralCode, ReferralStatus


def generate_referral_code(length: int = 8) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def get_or_create_referral_code(session: AsyncSession, user_id: UUID) -> ReferralCode:
    result = await session.execute(
        select(ReferralCode).where(ReferralCode.user_id == user_id),
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    for _ in range(10):
        code = generate_referral_code()
        conflict = await session.execute(
            select(ReferralCode).where(ReferralCode.code == code),
        )
        if conflict.scalar_one_or_none() is None:
            referral_code = ReferralCode(user_id=user_id, code=code)
            session.add(referral_code)
            await session.flush()
            return referral_code
    raise RuntimeError("Failed to generate unique referral code")


async def get_referral_code_by_code(session: AsyncSession, code: str) -> ReferralCode | None:
    result = await session.execute(
        select(ReferralCode).where(ReferralCode.code == code),
    )
    return result.scalar_one_or_none()


async def create_referral(
    session: AsyncSession,
    *,
    referrer_id: UUID,
    invitee_id: UUID,
) -> Referral | None:
    if referrer_id == invitee_id:
        return None
    existing = await session.execute(
        select(Referral).where(Referral.invitee_id == invitee_id),
    )
    if existing.scalar_one_or_none():
        return None
    referral = Referral(referrer_id=referrer_id, invitee_id=invitee_id)
    session.add(referral)
    await session.flush()
    return referral


async def count_referrals(session: AsyncSession, referrer_id: UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(Referral).where(
            Referral.referrer_id == referrer_id,
            Referral.status == ReferralStatus.REWARDED,
        ),
    )
    return int(result.scalar_one())


async def get_pending_referral_for_invitee(
    session: AsyncSession,
    invitee_id: UUID,
) -> Referral | None:
    result = await session.execute(
        select(Referral).where(
            Referral.invitee_id == invitee_id,
            Referral.status == ReferralStatus.PENDING,
        ),
    )
    return result.scalar_one_or_none()
