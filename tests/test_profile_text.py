from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from astra.telegram.profile_text import (
    format_profile_card,
    shorten_city_label,
    shorten_place_display,
)


def test_shorten_place_display() -> None:
    assert shorten_place_display("Козет, Республика Адыгея, Россия") == "Козет, Адыгея"
    assert shorten_city_label("Краснодар, Краснодарский край, Россия") == "Краснодар"


def test_profile_card_a2_layout() -> None:
    user = SimpleNamespace(points=7, streak_current=1)
    profile = SimpleNamespace(
        display_name="Aidamir",
        birth_date=date(1998, 2, 14),
        birth_time=datetime(1998, 2, 14, 0, 34, tzinfo=timezone.utc),
        birth_place="Козет, Республика Адыгея, Россия",
        notification_place_id=uuid4(),
        city="Краснодар, Краснодарский край, Россия",
        timezone="Europe/Moscow",
    )
    text = format_profile_card(user, profile)
    assert text.startswith("✨ Твой профиль")
    assert "👤 <b>Aidamir</b>" in text
    assert "📅 14.02.1998" in text
    assert "🕐 " in text
    assert "📍 Козет, Адыгея" in text
    assert "🌍 Краснодар" in text
    assert "Europe/Moscow" in text
    assert "──────────────" in text
    assert "🔥 Серия 1 дн." in text
    assert "⭐ 7 баллов" in text
    assert "Дата:" not in text
    assert "Краснодарский край" not in text


def test_profile_card_hints_when_incomplete() -> None:
    user = SimpleNamespace(points=0, streak_current=0)
    profile = SimpleNamespace(
        display_name="Тест",
        birth_date=date(2000, 1, 1),
        birth_time=None,
        birth_place="",
        notification_place_id=None,
        city="не указан",
        timezone="Europe/Moscow",
    )
    text = format_profile_card(user, profile)
    assert "время рождения" in text.lower()
    assert "место рождения" in text.lower()
