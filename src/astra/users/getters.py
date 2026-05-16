from datetime import datetime, time
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from astra.users import crud
from astra.users.models import Profile, User
from astra.users.schemas import ProfileRead, UserMeRead, UserRead


def calculate_profile_accuracy(profile: Profile) -> tuple[int, str]:
    has_time = profile.birth_time is not None
    has_place = profile.birth_place is not None and profile.birth_place.strip() != ""

    if has_time and has_place:
        return 100, "Максимальная точность ✨"
    if has_time:
        return 66, "Дозаполни место рождения в профиле — будет точнее."
    return 33, "Дозаполни время и место рождения в профиле — будет точнее."


def profile_to_read(profile: Profile) -> ProfileRead:
    accuracy, hint = calculate_profile_accuracy(profile)
    birth_time_value: time | None = None
    if profile.birth_time is not None:
        birth_time_value = profile.birth_time.time()
    return ProfileRead(
        display_name=profile.display_name,
        birth_date=profile.birth_date,
        birth_time=birth_time_value,
        birth_place=profile.birth_place,
        city=profile.city,
        timezone=profile.timezone,
        accuracy_percent=accuracy,
        accuracy_hint=hint,
    )


async def get_user_me(session: AsyncSession, user_id: UUID) -> UserMeRead | None:
    user = await crud.get_user_by_id(session, user_id)
    if user is None:
        return None
    profile_read = profile_to_read(user.profile) if user.profile else None
    return UserMeRead(
        user=UserRead.model_validate(user),
        profile=profile_read,
    )
