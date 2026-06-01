"""Текст карточки «Профиль» в Telegram (вариант A2)."""

from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from astra.places.normalize import normalize_place_query

_SEPARATOR = "──────────────"

_HINT_BIRTH_TIME = (
    "🕐 <i>Добавь время рождения в профиле — так я попаду в натал точнее ✨</i>"
)
_HINT_BIRTH_PLACE = (
    "📍 <i>Добавь место рождения в профиле — небо станет понятнее 🌙</i>"
)
_HINT_NOTIFICATION_CITY = (
    "🌍 <i>Выбери город для уведомлений в профиле — "
    "пришлю предсказание в 09:00 по твоему времени</i>"
)


class _ProfileView(Protocol):
    display_name: str
    birth_date: date
    birth_time: datetime | None
    birth_place: str | None
    notification_place_id: object | None
    city: str
    timezone: str


class _UserView(Protocol):
    points: int
    streak_current: int


def _shorten_admin_part(part: str) -> str:
    part = part.strip()
    if part.startswith("Республика "):
        return part.removeprefix("Республика ").strip()
    return part


def shorten_place_display(full: str) -> str:
    """Козет, Республика Адыгея, Россия → Козет, Адыгея."""
    text = full.strip()
    if not text:
        return text
    if text.endswith(", Россия"):
        text = text[: -len(", Россия")].strip()
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if not parts:
        return full.strip()
    if len(parts) == 1:
        return _shorten_admin_part(parts[0])
    city = _shorten_admin_part(parts[0])
    region = _shorten_admin_part(parts[1])
    if region and normalize_place_query(region) != normalize_place_query(city):
        return f"{city}, {region}"
    return city


def shorten_city_label(full: str) -> str:
    """Краснодар, Краснодарский край, Россия → Краснодар."""
    text = full.strip()
    if text.endswith(", Россия"):
        text = text[: -len(", Россия")].strip()
    if not text:
        return text
    return text.split(",")[0].strip()


def _format_birth_time_line(profile: _ProfileView) -> str:
    if profile.birth_time is None:
        return _HINT_BIRTH_TIME
    bt = profile.birth_time
    if bt.tzinfo is not None:
        bt = bt.astimezone(ZoneInfo(profile.timezone))
    return f"🕐 {bt.strftime('%H:%M')}"


def _format_birth_place_line(profile: _ProfileView) -> str:
    place = (profile.birth_place or "").strip()
    if not place:
        return _HINT_BIRTH_PLACE
    return f"📍 {shorten_place_display(place)}"


def _format_notification_block(profile: _ProfileView) -> list[str]:
    if profile.notification_place_id is None:
        return [_HINT_NOTIFICATION_CITY]
    city = shorten_city_label(profile.city)
    try:
        clock = datetime.now(ZoneInfo(profile.timezone)).strftime("%H:%M")
        return [f"🌍 {city}", f"   {clock} · {profile.timezone}"]
    except Exception:
        return [f"🌍 {city}", f"   {profile.timezone}"]


def format_profile_card(user: _UserView, profile: _ProfileView) -> str:
    lines = [
        "✨ Твой профиль",
        "",
        f"👤 <b>{profile.display_name}</b>",
        "",
        f"📅 {profile.birth_date.strftime('%d.%m.%Y')}",
        _format_birth_time_line(profile),
        _format_birth_place_line(profile),
        "",
        *_format_notification_block(profile),
        "",
        _SEPARATOR,
        f"🔥 Серия {user.streak_current} дн.  ·  ⭐ {user.points} баллов",
    ]
    return "\n".join(lines)
