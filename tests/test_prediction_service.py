from datetime import date
from types import SimpleNamespace

from astra.services.prediction_service import (
    _zodiac_sign,
    format_prediction_for_user,
    format_prediction_message,
    generate_prediction_body,
)


def test_zodiac_sign() -> None:
    assert _zodiac_sign(date(1990, 3, 25)) == "Овен"


def test_generate_prediction_body() -> None:
    body = generate_prediction_body()
    assert body
    assert "✨" not in body
    assert "Точность" not in body


def _profile(**overrides: object) -> SimpleNamespace:
    base = {
        "display_name": "Маша",
        "birth_date": date(1995, 7, 20),
        "birth_time": None,
        "birth_place": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_format_prediction_message() -> None:
    profile = _profile()
    body = "Сегодня звёзды советуют довериться интуиции — важный знак уже рядом."
    message = format_prediction_message(profile, body, points=14, streak=2)
    assert "Маша" in message
    assert body in message
    assert "14" in message
    assert "2" in message
    assert "33%" in message


def test_format_prediction_for_user() -> None:
    profile = _profile(display_name="Aidamir", birth_date=date(1990, 3, 15))
    user = SimpleNamespace(points=7, streak_current=1)
    prediction = SimpleNamespace(
        text="Сегодня звёзды советуют довериться интуиции — важный знак уже рядом.",
    )
    message = format_prediction_for_user(prediction, user, profile)
    assert prediction.text in message
    assert "Aidamir" in message
    assert "7" in message
