"""Текст экрана «Изменить данные» в Telegram (вариант A2).

Раньше это была и главная карточка «Обо мне». Теперь «Обо мне» показывает
портрет по натальной карте (`profile_portrait.py`), а здесь — только сами
поля: что вписано и чего не хватает.
"""

from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from astra.astro.birth_time import format_birth_time
from astra.places.normalize import normalize_place_query
from astra.users.gender import Gender, gender_display_label

_SEPARATOR = "──────────────"

_HINT_BIRTH_DATE = (
    "📅 <i>Дата рождения пока не указана — спрошу её, когда откроешь разбор ✨</i>"
)
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
_HINT_GENDER = (
    "⚧ <i>Укажи пол в профиле — так формулировки в разборе будут точнее</i>"
)


class _ProfileView(Protocol):
    display_name: str
    gender: Gender | None
    birth_date: date | None
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
    if not region:
        return city
    city_key = normalize_place_query(city)
    region_key = normalize_place_query(region)
    # «Краснодар, Краснодарский край» — регион ничего не добавляет к городу.
    if region_key == city_key or region_key.startswith(city_key):
        return city
    return f"{city}, {region}"


def shorten_city_label(full: str) -> str:
    """Краснодар, Краснодарский край, Россия → Краснодар."""
    text = full.strip()
    if text.endswith(", Россия"):
        text = text[: -len(", Россия")].strip()
    if not text:
        return text
    return text.split(",")[0].strip()


def _format_gender_line(profile: _ProfileView) -> str:
    label = gender_display_label(profile.gender)
    if label is None:
        return _HINT_GENDER
    return label


def _format_birth_date_line(profile: _ProfileView) -> str:
    if profile.birth_date is None:
        return _HINT_BIRTH_DATE
    return f"📅 {profile.birth_date.strftime('%d.%m.%Y')}"


def _format_birth_time_line(profile: _ProfileView) -> str:
    label = format_birth_time(profile.birth_time)
    return f"🕐 {label}" if label else _HINT_BIRTH_TIME


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
        "✏️ Твои данные",
        "",
        f"👤 <b>{profile.display_name}</b>",
        "",
        _format_gender_line(profile),
        _format_birth_date_line(profile),
        _format_birth_time_line(profile),
        _format_birth_place_line(profile),
        "",
        *_format_notification_block(profile),
        "",
        _SEPARATOR,
        f"🔥 Серия {user.streak_current} дн.  ·  ⭐ {user.points} баллов",
    ]
    return "\n".join(lines)
