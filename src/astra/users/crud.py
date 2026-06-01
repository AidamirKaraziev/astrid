import logging
from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from astra.places import crud as places_crud
from astra.users.models import Profile, User

logger = logging.getLogger(__name__)

_ASTRO_PROFILE_FIELDS = ("birth_date", "birth_time", "birth_place", "birth_place_id")


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
    birth_place_id: UUID,
    birth_place: str,
    notification_place_id: UUID | None = None,
    city: str,
    timezone: str,
) -> Profile:
    profile = Profile(
        user_id=user_id,
        display_name=display_name,
        birth_date=birth_date,
        birth_place_id=birth_place_id,
        notification_place_id=notification_place_id,
        birth_place=birth_place,
        city=city,
        timezone=timezone,
    )
    session.add(profile)
    await session.flush()
    await _try_refresh_natal_chart(session, profile)
    return profile


async def _resolve_birth_place_id(
    session: AsyncSession,
    profile: Profile,
    birth_place: str,
) -> None:
    places = await places_crud.search_places(session, birth_place, limit=1)
    if not places:
        return
    best = places[0]
    profile.birth_place_id = best.id
    profile.birth_place = best.display_name


async def _invalidate_today_predictions_if_astro_changed(
    session: AsyncSession,
    profile: Profile,
    before: dict[str, object],
) -> None:
    changed = any(getattr(profile, key) != before[key] for key in _ASTRO_PROFILE_FIELDS)
    if not changed:
        return
    from astra.predictions import crud as predictions_crud

    today = datetime.now(ZoneInfo(profile.timezone)).date()
    deleted = await predictions_crud.delete_predictions_for_date(
        session,
        profile.user_id,
        today,
    )
    if deleted:
        logger.info(
            "Removed %s prediction(s) for user %s on %s after profile astro change",
            deleted,
            profile.user_id,
            today,
        )


async def update_profile(
    session: AsyncSession,
    profile: Profile,
    **fields: object,
) -> Profile:
    before = {key: getattr(profile, key) for key in _ASTRO_PROFILE_FIELDS}
    birth_place_text = fields.get("birth_place")
    for key, value in fields.items():
        if value is not None and hasattr(profile, key):
            setattr(profile, key, value)
    if isinstance(birth_place_text, str) and birth_place_text.strip():
        await _resolve_birth_place_id(session, profile, birth_place_text.strip())
    await _invalidate_today_predictions_if_astro_changed(session, profile, before)
    await session.flush()
    await _try_refresh_natal_chart(session, profile)
    return profile


async def _try_refresh_natal_chart(session: AsyncSession, profile: Profile) -> None:
    from astra.services.astro_service import refresh_natal_chart_for_profile

    try:
        await refresh_natal_chart_for_profile(session, profile)
    except Exception:
        logger.exception("natal chart refresh failed for profile %s", profile.id)
