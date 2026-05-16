from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from astra.users.models import Profile, User


async def get_user_by_telegram_id(
    session: AsyncSession,
    telegram_id: int,
) -> User | None:
    result = await session.execute(
        select(User)
        .where(User.telegram_id == telegram_id)
        .options(selectinload(User.profile), selectinload(User.referral_code)),
    )
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    result = await session.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.profile), selectinload(User.referral_code)),
    )
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: str | None,
    language_code: str | None,
) -> User:
    user = User(
        telegram_id=telegram_id,
        username=username,
        language_code=language_code,
    )
    session.add(user)
    await session.flush()
    return user


async def create_profile(
    session: AsyncSession,
    *,
    user_id: UUID,
    display_name: str,
    birth_date: date,
    city: str,
    timezone: str,
) -> Profile:
    profile = Profile(
        user_id=user_id,
        display_name=display_name,
        birth_date=birth_date,
        city=city,
        timezone=timezone,
    )
    session.add(profile)
    await session.flush()
    return profile


async def update_profile(
    session: AsyncSession,
    profile: Profile,
    **fields: object,
) -> Profile:
    for key, value in fields.items():
        if value is not None and hasattr(profile, key):
            setattr(profile, key, value)
    await session.flush()
    return profile
