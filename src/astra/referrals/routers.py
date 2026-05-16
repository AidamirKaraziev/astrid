from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from astra.db.session import get_session
from astra.referrals.getters import get_referral_stats
from astra.referrals.schemas import ReferralStatsRead
from astra.users import crud as users_crud

router = APIRouter(prefix="/referrals", tags=["referrals"])


@router.get("/stats/{user_id}", response_model=ReferralStatsRead)
async def referral_stats(
    user_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ReferralStatsRead:
    user = await users_crud.get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return await get_referral_stats(session, user_id)
