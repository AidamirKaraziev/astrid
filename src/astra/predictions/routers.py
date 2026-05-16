from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from astra.db.session import get_session
from astra.predictions.getters import get_today_prediction
from astra.predictions.schemas import PredictionRead
from astra.users import crud as users_crud

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/today/{user_id}", response_model=PredictionRead)
async def prediction_today(
    user_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> PredictionRead:
    user = await users_crud.get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    data = await get_today_prediction(session, user_id)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No prediction for today",
        )
    return data
