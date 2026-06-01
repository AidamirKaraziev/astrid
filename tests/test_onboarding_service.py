from datetime import date
from uuid import uuid4

import pytest

from astra.services.onboarding_service import OnboardingRegistrationData, parse_registration_fsm


def test_registration_from_fsm_ok() -> None:
    user_id = uuid4()
    birth_place_id = uuid4()
    notification_place_id = uuid4()
    reg = OnboardingRegistrationData.from_fsm(
        {
            "user_id": str(user_id),
            "display_name": "Аида",
            "birth_date": "1990-03-15",
            "birth_place_id": str(birth_place_id),
            "notification_place_id": str(notification_place_id),
            "birth_place_display": "Москва",
            "notification_place_display": "Казань",
            "notification_timezone": "Europe/Moscow",
        },
    )
    assert reg.user_id == user_id
    assert reg.display_name == "Аида"
    assert reg.birth_date == date(1990, 3, 15)
    assert reg.birth_place_id == birth_place_id
    assert reg.notification_place_id == notification_place_id
    assert reg.birth_place_display == "Москва"
    assert reg.notification_place_display == "Казань"


def test_parse_registration_fsm_missing_fields() -> None:
    assert parse_registration_fsm({"user_id": str(uuid4())}) is None


def test_parse_registration_fsm_empty_name() -> None:
    assert (
        parse_registration_fsm(
            {
                "user_id": str(uuid4()),
                "display_name": "   ",
                "birth_date": "1990-03-15",
                "birth_place_id": str(uuid4()),
                "notification_place_id": str(uuid4()),
            },
        )
        is None
    )


def test_registration_from_fsm_after_notification_place() -> None:
    """Данные для сохранения профиля собираются после выбора города проживания."""
    user_id = uuid4()
    reg = OnboardingRegistrationData.from_fsm(
        {
            "user_id": str(user_id),
            "display_name": "Тест",
            "birth_date": "2000-01-01",
            "birth_place_id": str(uuid4()),
            "notification_place_id": str(uuid4()),
            "notification_place_display": "Санкт-Петербург",
            "notification_timezone": "Europe/Moscow",
        },
    )
    assert reg.notification_place_display == "Санкт-Петербург"


def test_registration_from_fsm_invalid_date() -> None:
    with pytest.raises(ValueError):
        OnboardingRegistrationData.from_fsm(
            {
                "user_id": str(uuid4()),
                "display_name": "Test",
                "birth_date": "not-a-date",
                "birth_place_id": str(uuid4()),
                "notification_place_id": str(uuid4()),
            },
        )
