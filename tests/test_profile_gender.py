import pytest

from astra.users.gender import GENDER_FEMALE, GENDER_MALE, gender_display_label, normalize_gender
from astra.users.getters import profile_to_read
from astra.users.schemas import ProfileRead, ProfileUpdate


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("мужчина", GENDER_MALE),
        ("Мужчина", GENDER_MALE),
        (" женщина ", GENDER_FEMALE),
        (None, None),
        ("", None),
        ("other", None),
    ],
)
def test_normalize_gender(raw: str | None, expected: str | None) -> None:
    assert normalize_gender(raw) == expected


def test_gender_display_label() -> None:
    assert gender_display_label(GENDER_MALE) == "👨 Мужчина"
    assert gender_display_label(GENDER_FEMALE) == "👩 Женщина"
    assert gender_display_label(None) is None


def test_profile_update_accepts_gender() -> None:
    payload = ProfileUpdate(gender=GENDER_MALE)
    assert payload.gender == GENDER_MALE


def test_profile_update_rejects_invalid_gender() -> None:
    with pytest.raises(ValueError, match="gender must be"):
        ProfileUpdate(gender="робот")  # type: ignore[arg-type]


def test_profile_read_includes_gender() -> None:
    profile = ProfileRead(
        display_name="Аида",
        gender=GENDER_FEMALE,
        birth_date=__import__("datetime").date(1990, 3, 15),
        birth_time=None,
        birth_place="Москва",
        city="Москва",
        timezone="Europe/Moscow",
        accuracy_percent=100,
        accuracy_hint="ok",
    )
    assert profile.gender == GENDER_FEMALE


def test_profile_to_read_maps_gender() -> None:
    from datetime import date
    from types import SimpleNamespace

    profile = SimpleNamespace(
        display_name="Аида",
        gender=GENDER_FEMALE,
        birth_date=date(1990, 3, 15),
        birth_time=None,
        birth_place="Москва",
        city="Москва",
        timezone="Europe/Moscow",
    )
    read = profile_to_read(profile)  # type: ignore[arg-type]
    assert read.gender == GENDER_FEMALE
