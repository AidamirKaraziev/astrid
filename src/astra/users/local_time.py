"""Локальный день пользователя — единая точка на весь проект.

Серии, лимиты «раз в день» и активность считаются по дате человека, а не
сервера: в контейнере UTC, и для пользователя восточнее полночь наступает
раньше, чем сервер переведёт дату.

До появления этого модуля такая функция была написана дважды (в таро и в
колесе) и обе падали, если профиля ещё нет. Здесь профиль необязателен:
у человека без онбординга берём московское время.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from astra.users.models import User

DEFAULT_TIMEZONE = "Europe/Moscow"


def user_timezone(user: User) -> ZoneInfo:
    """Таймзона из профиля; у пользователя без профиля — умолчание."""
    name = user.profile.timezone if user.profile is not None else DEFAULT_TIMEZONE
    try:
        return ZoneInfo(name or DEFAULT_TIMEZONE)
    except Exception:
        # Мусор в базе не должен ронять начисление серии.
        return ZoneInfo(DEFAULT_TIMEZONE)


def local_today(user: User) -> date:
    """Сегодняшняя дата в часовом поясе человека."""
    return datetime.now(user_timezone(user)).date()
