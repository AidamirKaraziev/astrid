"""Транзитные окна: когда медленная планета подходит к точке карты.

Общий движок раздела «Спроси Астрид», продуктонезависимый. Считаем прямо через
swisseph (эфемериды Moshier — файлы не нужны): помесячно идём по жизни человека
и ищем, когда Сатурн, Юпитер или Уран подходят к заданным точкам. Соседние
месяцы схлопываются в одно окно с пиком.

Какие точки и с каким весом смотреть — решает продукт: у партнёрства это
десцендент и Венера, у детей — 5 дом и Луна. Быстрые планеты не берём вовсе:
они активируют карту ежемесячно и «событием» быть не могут.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date

from pydantic import BaseModel


class TransitWindow(BaseModel):
    """Окно активации: транзит медленной планеты к точке карты."""

    start: date
    peak: date
    end: date
    transit: str  # «Сатурн», «Юпитер», «Уран»
    target: str  # что именно активируется: «десцендент», «5 дом», «Луна»
    weight: float  # вклад окна: чем выше, тем крупнее событие
    age: int  # возраст человека на пике окна


def window_period(window: TransitWindow) -> str:
    """Период окна человеческими словами: «2029» или «2029–2030»."""
    if window.start.year == window.end.year:
        return str(window.peak.year)
    return f"{window.start.year}–{window.end.year}"


# Раньше этого возраста событие не считаем значимым даже при точном транзите.
MIN_AGE = 16
# Насколько вперёд смотрим будущие окна.
FUTURE_YEARS = 15

_ORB_DEG = 3.0

# (планета swisseph, подпись) — только медленные.
_TRANSIT_PLANETS: tuple[tuple[str, str], ...] = (
    ("SATURN", "Сатурн"),
    ("JUPITER", "Юпитер"),
    ("URANUS", "Уран"),
)

# Окно считается сильным (=«полноценная история»), если вес пика не ниже.
STRONG_WEIGHT = 0.8


def _angular_distance(a: float, b: float) -> float:
    diff = abs(a - b) % 360.0
    return min(diff, 360.0 - diff)


def _month_ends(start: date, end: date) -> list[date]:
    """Первое число каждого месяца в диапазоне."""
    months: list[date] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(date(year, month, 1))
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return months


def _longitude(planet: str, moment: date) -> float | None:
    """Долгота планеты на полдень UT. None, если эфемериды недоступны."""
    import swisseph as swe

    jd = swe.julday(moment.year, moment.month, moment.day, 12.0)
    try:
        result = swe.calc_ut(jd, getattr(swe, planet), swe.FLG_MOSEPH)
    except Exception:
        return None
    return float(result[0][0])


def _last_day(moment: date) -> date:
    return moment.replace(day=monthrange(moment.year, moment.month)[1])


def find_windows(
    targets: dict[str, float],
    *,
    weights: dict[tuple[str, str], float],
    birth_date: date,
    today: date,
    min_age: int = MIN_AGE,
    future_years: int = FUTURE_YEARS,
) -> list[TransitWindow]:
    """Окна за прожитую жизнь и вперёд, отсортированные по времени.

    `targets` — подпись точки → её долгота; `weights` — вес пары
    «транзитная планета × точка», он же задаёт, какие пары вообще считать.
    Таблица весов своя у каждого продукта: для детей важен Юпитер к 5 дому,
    для партнёрства — Сатурн к десценденту.
    """
    if not targets:
        return []

    start = date(birth_date.year + min_age, birth_date.month, min(birth_date.day, 28))
    end = date(today.year + future_years, today.month, 1)
    months = _month_ends(start, end)

    windows: list[TransitWindow] = []
    for planet, planet_ru in _TRANSIT_PLANETS:
        longitudes = [(moment, _longitude(planet, moment)) for moment in months]
        if any(lon is None for _, lon in longitudes):
            return []  # эфемериды недоступны — окна не выдумываем

        for target_name, target_lon in targets.items():
            weight = weights.get((planet_ru, target_name))
            if weight is None:
                continue
            windows.extend(
                _windows_for_pair(
                    longitudes,  # type: ignore[arg-type]
                    target_lon=target_lon,
                    target_name=target_name,
                    planet_ru=planet_ru,
                    weight=weight,
                    birth_date=birth_date,
                ),
            )

    windows.sort(key=lambda w: w.peak)
    return windows


def _windows_for_pair(
    longitudes: list[tuple[date, float]],
    *,
    target_lon: float,
    target_name: str,
    planet_ru: str,
    weight: float,
    birth_date: date,
) -> list[TransitWindow]:
    """Слепить подряд идущие месяцы «в орбисе» в одно окно с пиком."""
    windows: list[TransitWindow] = []
    run: list[tuple[date, float]] = []  # (месяц, расстояние до точки)

    def _flush() -> None:
        if not run:
            return
        peak_month, _ = min(run, key=lambda item: item[1])
        windows.append(
            TransitWindow(
                start=run[0][0],
                peak=peak_month,
                end=_last_day(run[-1][0]),
                transit=planet_ru,
                target=target_name,
                weight=weight,
                age=_age_at(birth_date, peak_month),
            ),
        )
        run.clear()

    for moment, lon in longitudes:
        distance = _angular_distance(lon, target_lon)
        if distance <= _ORB_DEG:
            run.append((moment, distance))
        else:
            _flush()
    _flush()
    return windows


def _age_at(birth_date: date, moment: date) -> int:
    years = moment.year - birth_date.year
    if (moment.month, moment.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def split_by_today(
    windows: list[TransitWindow],
    *,
    today: date,
) -> tuple[list[TransitWindow], list[TransitWindow]]:
    """Разделить окна на прожитые и предстоящие. Текущее окно — предстоящее."""
    past = [w for w in windows if w.end < today]
    future = [w for w in windows if w.end >= today]
    return past, future


def merge_overlapping(windows: list[TransitWindow]) -> list[TransitWindow]:
    """Схлопнуть пересекающиеся окна разных планет в одну историю.

    Сатурн к десценденту и Юпитер к Венере в один и тот же год — это один
    человек, а не двое. Оставляем окно с большим весом.
    """
    merged: list[TransitWindow] = []
    for window in sorted(windows, key=lambda w: w.peak):
        if merged and (window.peak - merged[-1].peak).days <= 365:
            if window.weight > merged[-1].weight:
                merged[-1] = window
            continue
        merged.append(window)
    return merged
