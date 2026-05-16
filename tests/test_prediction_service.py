from datetime import date

from astra.services.prediction_service import _zodiac_sign, build_prediction_text
from astra.users.models import Profile


def test_zodiac_sign() -> None:
    assert _zodiac_sign(date(1990, 3, 25)) == "Овен"


def test_build_prediction_text() -> None:
    profile = Profile(
        user_id=__import__("uuid").uuid4(),
        display_name="Маша",
        birth_date=date(1995, 7, 20),
        city="Казань",
        timezone="Europe/Moscow",
    )
    text, accuracy = build_prediction_text(profile, points=14, streak=2)
    assert "Маша" in text
    assert accuracy == 33
    assert "14" in text
    assert "2" in text
