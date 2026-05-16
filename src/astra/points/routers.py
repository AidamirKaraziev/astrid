from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from astra.db.session import get_session
from astra.points.getters import get_points_balance
from astra.points.schemas import PointsBalanceRead

router = APIRouter(prefix="/points", tags=["points"])


@router.get("/balance/{user_id}", response_model=PointsBalanceRead)
async def points_balance(
    user_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> PointsBalanceRead:
    data = await get_points_balance(session, user_id)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return data
