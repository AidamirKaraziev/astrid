"""Время рождения — настенные часы места рождения, и никогда не момент.

Баг, который эти тесты держат закрытым: человек вписал 03:35, а бот показывал
06:35 и считал карту на 06:35. Колонка была `timestamptz`, хендлеры клали
наивный `datetime`, драйвер трактовал его в поясе процесса (в Docker — UTC),
а на чтении `astimezone` сдвигал часы ещё раз.
"""

import re
from datetime import date, datetime, time, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from astra.astro.birth_time import (
    WallClock,
    as_wall_clock,
    birth_local_datetime,
    format_birth_time,
    wall_clock_at,
    with_birth_date,
)

_ENTERED = time(3, 35)
_BIRTH_DATE = date(1998, 2, 14)
_ARMAVIR_TZ = "Europe/Moscow"


# ── Семантика ───────────────────────────────────────────────────────────────


def test_entered_time_survives_the_round_trip() -> None:
    stored = wall_clock_at(_BIRTH_DATE, _ENTERED)

    assert stored.tzinfo is None
    assert format_birth_time(stored) == "03:35"


def test_aware_value_keeps_its_digits() -> None:
    """Старые строки с поясом: цифры в них и есть настенные часы."""
    legacy = datetime(1998, 2, 14, 3, 35, tzinfo=timezone.utc)

    assert as_wall_clock(legacy) == datetime(1998, 2, 14, 3, 35)
    assert format_birth_time(legacy) == "03:35"


def test_chart_gets_the_entered_hour_in_the_birth_place_zone() -> None:
    moment = birth_local_datetime(_BIRTH_DATE, wall_clock_at(_BIRTH_DATE, _ENTERED), _ARMAVIR_TZ)

    assert (moment.hour, moment.minute) == (3, 35)
    assert moment.tzinfo == ZoneInfo(_ARMAVIR_TZ)
    # 1998-й в России — MSK+0 зимой, то есть UTC+3; пояс приделан, а не пересчитан
    assert moment.utcoffset().total_seconds() == 3 * 3600


def test_legacy_aware_value_does_not_shift_the_chart() -> None:
    """Ровно тот баг: без срезания пояса тут получилось бы 06:35."""
    legacy = datetime(1998, 2, 14, 3, 35, tzinfo=timezone.utc)

    moment = birth_local_datetime(_BIRTH_DATE, legacy, _ARMAVIR_TZ)

    assert (moment.hour, moment.minute) == (3, 35)


def test_unknown_time_falls_back_to_noon() -> None:
    moment = birth_local_datetime(_BIRTH_DATE, None, _ARMAVIR_TZ)

    assert (moment.hour, moment.minute) == (12, 0)
    assert moment.tzinfo == ZoneInfo(_ARMAVIR_TZ)


def test_moving_the_date_keeps_the_hour() -> None:
    moved = with_birth_date(wall_clock_at(_BIRTH_DATE, _ENTERED), date(1999, 5, 1))

    assert moved == datetime(1999, 5, 1, 3, 35)
    assert moved.tzinfo is None


def test_unknown_time_stays_none() -> None:
    assert as_wall_clock(None) is None
    assert with_birth_date(None, _BIRTH_DATE) is None
    assert format_birth_time(None) is None


# ── Гарантия на уровне типа колонки ─────────────────────────────────────────


def test_column_type_cannot_store_a_moment() -> None:
    """Пояс срезается в самом типе — договорённости между хендлерами мало."""
    column = WallClock()

    bound = column.process_bind_param(datetime(1998, 2, 14, 3, 35, tzinfo=timezone.utc), None)
    assert bound == datetime(1998, 2, 14, 3, 35)
    assert bound.tzinfo is None

    loaded = column.process_result_value(datetime(1998, 2, 14, 3, 35), None)
    assert loaded.tzinfo is None


def test_column_is_timestamp_without_time_zone() -> None:
    assert WallClock().impl_instance.timezone is False


def test_models_use_the_wall_clock_column() -> None:
    from astra.compatibility.models import NatalProfile
    from astra.users.models import Profile

    for model in (Profile, NatalProfile):
        column = model.__table__.c.birth_time
        assert isinstance(column.type, WallClock), model.__name__


# ── Защита от возврата конверсий ────────────────────────────────────────────


def test_no_module_converts_birth_time_between_zones() -> None:
    """`astimezone` над временем рождения — и есть тот самый баг.

    Ловим по имени переменной: `bt` и `birth_time` — так назывались все пять
    мест, где часы сдвигались. Общее `moment` в шаблон не берём: под этим
    именем в проекте живут «сейчас» для серии дней и таймстемпы логов, и там
    перевод пояса как раз уместен.
    """
    suspicious = re.compile(r"\b(bt|birth_time)\s*\.\s*astimezone")
    offenders = [
        f"{path}:{number}"
        for path in Path("src/astra").rglob("*.py")
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if suspicious.search(line)
    ]

    assert not offenders, f"время рождения переводится между поясами: {offenders}"


# ── Сквозной путь: ввод → показ → расчёт ────────────────────────────────────


@pytest.mark.anyio
async def test_entered_time_reaches_card_and_chart_unchanged() -> None:
    from astra.telegram.handlers.menu import save_birth_time
    from astra.telegram.profile_portrait import format_portrait_card

    message = AsyncMock()
    message.text = "03:35"
    message.from_user.id = 42
    profile = SimpleNamespace(
        id=uuid4(),
        display_name="Aidamir",
        gender="мужчина",
        birth_date=_BIRTH_DATE,
        birth_time=None,
        birth_place="Армавир, Краснодарский край, Россия",
        birth_place_id=uuid4(),
        notification_place_id=uuid4(),
        city="Армавир, Краснодарский край, Россия",
        timezone=_ARMAVIR_TZ,
    )
    user = SimpleNamespace(points=0, streak_current=1, profile=profile)

    saved: dict[str, object] = {}

    async def _capture(session, target, **fields):  # noqa: ANN001, ANN202
        saved.update(fields)
        target.birth_time = fields.get("birth_time")
        return target

    with (
        patch(
            "astra.telegram.handlers.menu._get_user",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch("astra.telegram.handlers.menu.users_crud.update_profile", new=_capture),
        patch("astra.telegram.handlers.menu._send_portrait", new_callable=AsyncMock),
    ):
        await save_birth_time(message, AsyncMock(), AsyncMock())

    # в базу уходят настенные часы
    assert saved["birth_time"] == datetime(1998, 2, 14, 3, 35)
    assert saved["birth_time"].tzinfo is None

    # в карточке — ровно они же
    card = format_portrait_card(user, profile, None, has_birth_coords=True)
    assert "14 февраля 1998, 03:35" in card
    assert "06:35" not in card

    # и в расчёт уходят они же
    moment = birth_local_datetime(profile.birth_date, profile.birth_time, profile.timezone)
    assert (moment.hour, moment.minute) == (3, 35)
