from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from astra.db.session import get_session
from astra.users import crud
from astra.users.getters import get_user_me, profile_to_read
from astra.users.schemas import ProfileUpdate, UserMeRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me/{user_id}", response_model=UserMeRead)
async def read_user_me(
    user_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> UserMeRead:
    """MVP: user_id in path until JWT auth for web clients."""
    data = await get_user_me(session, user_id)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return data


@router.patch("/me/{user_id}/profile", response_model=UserMeRead)
async def patch_profile(
    user_id: UUID,
    payload: ProfileUpdate,
    session: AsyncSession = Depends(get_session),
) -> UserMeRead:
    user = await crud.get_user_by_id(session, user_id)
    if user is None or user.profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    update_data = payload.model_dump(exclude_unset=True)
    birth_date = update_data.get("birth_date", user.profile.birth_date)
    if "birth_time" in update_data and update_data["birth_time"] is not None:
        bt = update_data.pop("birth_time")
        from datetime import datetime

        update_data["birth_time"] = datetime.combine(birth_date, bt)
    if "birth_date" in update_data and user.profile.birth_time is not None:
        new_date = update_data["birth_date"]
        update_data["birth_time"] = user.profile.birth_time.replace(
            year=new_date.year,
            month=new_date.month,
            day=new_date.day,
        )

    await crud.update_profile(session, user.profile, **update_data)
    await session.refresh(user, attribute_names=["profile"])
    data = await get_user_me(session, user_id)
    assert data is not None
    return data
