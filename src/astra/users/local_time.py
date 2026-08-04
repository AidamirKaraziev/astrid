"""Локальный день пользователя — единая точка на весь проект.

Серии, лимиты «раз в день» и активность считаются по дате человека, а не
сервера: в контейнере UTC, и для пользователя восточнее полночь наступает
раньше, чем сервер переведёт дату.

До появления этого модуля такая функция была написана дважды (в таро и в
колесе) и обе падали, если профиля ещё нет. Здесь профиль необязателен:
у человека без онбординга берём московское время.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from astra.users.models import User

DEFAULT_TIMEZONE = "Europe/Moscow"


def user_timezone(user: User) -> ZoneInfo:
    """Таймзона из профиля; у пользователя без профиля — умолчание."""
    profile = user.__dict__.get("profile")
    name = profile.timezone if profile is not None else DEFAULT_TIMEZONE
    try:
        return ZoneInfo(name or DEFAULT_TIMEZONE)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def local_today(user: User, now: datetime | None = None) -> date:
    """Дата в часовом поясе человека; `now` — для тестов и пересчётов."""
    moment = now or datetime.now(UTC)
    return moment.astimezone(user_timezone(user)).date()
