"""Сохранение данных онбординга в users и profiles."""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from astra.places.getters import get_place_read
from astra.referrals import crud as referrals_crud
from astra.services.referral_service import complete_referral_rewards
from astra.users import crud as users_crud
from astra.users.models import Profile, User

logger = logging.getLogger(__name__)


class OnboardingRegistrationData(BaseModel):
    """Данные FSM, необходимые для завершения регистрации."""

    user_id: UUID
    display_name: str = Field(min_length=1, max_length=255)
    birth_date: date
    birth_place_id: UUID
    notification_place_id: UUID
    birth_place_display: str = ""
    notification_place_display: str = ""
    notification_timezone: str = "Europe/Moscow"

    @classmethod
    def from_fsm(cls, data: dict[str, object]) -> OnboardingRegistrationData:
        raw_user_id = data.get("user_id")
        raw_birth_date = data.get("birth_date")
        raw_birth_place_id = data.get("birth_place_id")
        raw_notification_place_id = data.get("notification_place_id")
        raw_display_name = data.get("display_name")

        if not all(
            (
                raw_user_id,
                raw_birth_date,
                raw_birth_place_id,
                raw_notification_place_id,
                raw_display_name,
            ),
        ):
            missing = [
                key
                for key, val in (
                    ("user_id", raw_user_id),
                    ("birth_date", raw_birth_date),
                    ("birth_place_id", raw_birth_place_id),
                    ("notification_place_id", raw_notification_place_id),
                    ("display_name", raw_display_name),
                )
                if not val
            ]
            raise ValueError(f"Не хватает данных онбординга: {', '.join(missing)}")

        birth_date = date.fromisoformat(str(raw_birth_date))
        display_name = str(raw_display_name).strip()
        if not display_name:
            raise ValueError("display_name пустой")

        return cls(
            user_id=UUID(str(raw_user_id)),
            display_name=display_name,
            birth_date=birth_date,
            birth_place_id=UUID(str(raw_birth_place_id)),
            notification_place_id=UUID(str(raw_notification_place_id)),
            birth_place_display=str(data.get("birth_place_display") or ""),
            notification_place_display=str(data.get("notification_place_display") or ""),
            notification_timezone=str(data.get("notification_timezone") or "Europe/Moscow"),
        )


async def sync_user_from_telegram(
    session: AsyncSession,
    user: User,
    *,
    username: str | None,
    language_code: str | None,
) -> None:
    """Обновить поля users из Telegram при каждом /start."""
    user.username = username
    user.language_code = language_code
    await session.flush()


def _profile_fields_from_registration(
    reg: OnboardingRegistrationData,
    *,
    timezone: str,
    city: str,
) -> dict[str, object]:
    return {
        "display_name": reg.display_name,
        "birth_date": reg.birth_date,
        "birth_place_id": reg.birth_place_id,
        "notification_place_id": reg.notification_place_id,
        "birth_place": reg.birth_place_display,
        "city": city,
        "timezone": timezone,
    }


async def _resolved_city_and_timezone(
    session: AsyncSession,
    reg: OnboardingRegistrationData,
) -> tuple[str, str]:
    timezone = reg.notification_timezone
    city = reg.notification_place_display
    notif_place = await get_place_read(session, reg.notification_place_id)
    if notif_place is not None:
        timezone = notif_place.timezone
        city = notif_place.display_name
    return city, timezone


async def save_profile_from_onboarding(
    session: AsyncSession,
    user: User,
    reg: OnboardingRegistrationData,
) -> Profile:
    """Записать профиль в БД после выбора города проживания (onboarding ещё не завершён)."""
    city, timezone = await _resolved_city_and_timezone(session, reg)
    profile_fields = _profile_fields_from_registration(reg, timezone=timezone, city=city)

    if user.profile is not None:
        return await users_crud.update_profile(session, user.profile, **profile_fields)
    return await users_crud.create_profile(session, user_id=user.id, **profile_fields)


async def finalize_onboarding(session: AsyncSession, user: User) -> None:
    """Завершить онбординг: флаг users, рефералы (профиль уже в БД)."""
    user.onboarding_completed = True
    await session.flush()

    try:
        await complete_referral_rewards(session, user)
    except Exception:
        logger.exception("referral rewards failed for user %s", user.id)

    try:
        await referrals_crud.get_or_create_referral_code(session, user.id)
    except Exception:
        logger.exception("referral code failed for user %s", user.id)


async def complete_registration(
    session: AsyncSession,
    user: User,
    reg: OnboardingRegistrationData,
) -> Profile:
    """Сохранить профиль и завершить онбординг (одной транзакцией)."""
    profile = await save_profile_from_onboarding(session, user, reg)
    await finalize_onboarding(session, user)
    return profile


async def run_registration_phase(
    session: AsyncSession,
    user: User,
    reg: OnboardingRegistrationData,
) -> Profile:
    """Этап 1: users + profiles + завершение онбординга."""
    return await complete_registration(session, user, reg)


def parse_registration_fsm(data: dict[str, object]) -> OnboardingRegistrationData | None:
    try:
        return OnboardingRegistrationData.from_fsm(data)
    except (ValidationError, ValueError, TypeError) as exc:
        logger.warning("invalid onboarding FSM data: %s data_keys=%s", exc, list(data.keys()))
        return None
