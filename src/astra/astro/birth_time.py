"""Время рождения — настенные часы места рождения. Единственная семантика.

Что это значит: `03:35` в свидетельстве о рождении — это `03:35` на часах
Армавира, а не момент времени. Момент получается только вместе с местом:
часы + координаты + правила часового пояса на ту дату. Поэтому в базе лежит
`TIMESTAMP WITHOUT TIME ZONE` (тип `WallClock` ниже), а пояс приезжает из
места рождения в момент расчёта (`birth_local_datetime`).

## Почему не «как правильнее», а именно так

Хранить момент в UTC не выйдет: человек меняет место рождения в профиле
позже, чем вписывает время, — и сохранённый момент молча начинает означать
другие настенные часы. Плюс исторические правила поясов (в России 1998-го
было летнее время, в 2011–2014 его не было) пришлось бы применять на запись,
а не на чтение.

## Баг, из-за которого это написано

Колонка была `timestamptz`, а хендлеры клали наивный `datetime`. Драйвер
трактует наивное значение в часовом поясе **процесса**, который пишет:

* бот запущен на машине с MSK → `03:35` уезжало в базу как `00:35Z`;
* бот в Docker (там UTC) → то же `03:35` уезжало как `03:35Z`.

На чтении показывали `astimezone(profile.timezone)`, и во втором случае
человек видел `06:35` вместо `03:35`, а натальная карта считалась на 06:35 —
асцендент уезжал почти на два знака. Значение строки зависело от того, где
крутился процесс в момент записи.

Правило теперь одно: **над `birth_time` не бывает `astimezone`**. Пояс
навешивается ровно один раз и только здесь.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator

# Время неизвестно — считаем от полудня: середина суток даёт наименьшую
# ошибку по Луне и не притворяется, что мы знаем час.
UNKNOWN_TIME_FALLBACK = time(12, 0)


class WallClock(TypeDecorator):
    """`TIMESTAMP WITHOUT TIME ZONE` с гарантией наивности значения.

    Момент времени сюда не положить: пояс срезается на записи, и в код из
    базы всегда приходит наивный `datetime`. Гарантия живёт в типе, а не в
    договорённости между хендлерами — их шесть, и каждый новый забудет.
    """

    impl = DateTime
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(timezone=False)

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:  # noqa: ANN001
        return as_wall_clock(value)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:  # noqa: ANN001
        return as_wall_clock(value)


def as_wall_clock(value: datetime | None) -> datetime | None:
    """Привести к настенным часам: срезать пояс, цифры не трогать.

    Именно срезать, а не переводить: у значений с поясом (старые строки,
    ручной ввод через API) цифры уже и есть те самые настенные часы —
    перевод сдвинул бы их второй раз.
    """
    if value is None:
        return None
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def wall_clock_at(birth_date: date, moment: time) -> datetime:
    """Собрать время рождения из даты и часов, которые назвал человек."""
    return datetime.combine(birth_date, moment)


def with_birth_date(birth_time: datetime | None, birth_date: date) -> datetime | None:
    """Переставить сохранённые часы на другую дату рождения."""
    if birth_time is None:
        return None
    return as_wall_clock(birth_time).replace(
        year=birth_date.year,
        month=birth_date.month,
        day=birth_date.day,
    )


def birth_local_datetime(
    birth_date: date,
    birth_time: datetime | None,
    timezone: str,
) -> datetime:
    """Момент рождения для эфемерид: настенные часы + пояс места рождения.

    Единственное место в проекте, где к времени рождения приделывается пояс.
    `ZoneInfo` сам разберётся с историческими правилами на нужную дату.
    """
    tz = ZoneInfo(timezone)
    moment = as_wall_clock(birth_time)
    if moment is None:
        return datetime.combine(birth_date, UNKNOWN_TIME_FALLBACK, tzinfo=tz)
    return moment.replace(tzinfo=tz)


def format_birth_time(birth_time: datetime | None) -> str | None:
    """ЧЧ:ММ для показа человеку. Ровно то, что он вписал."""
    moment = as_wall_clock(birth_time)
    return moment.strftime("%H:%M") if moment else None
