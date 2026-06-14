"""Упрощённый расчёт без kerykeion/pyswisseph (для Docker без gcc)."""

from datetime import date

from astra.astro.schemas import NatalChartData
from astra.users.getters import calculate_profile_accuracy
from astra.users.models import Profile


def _sun_sign(birth_date: date) -> str:
    d = (birth_date.month, birth_date.day)
    signs = [
        ((3, 21), (4, 19), "Овен"),
        ((4, 20), (5, 20), "Телец"),
        ((5, 21), (6, 20), "Близнецы"),
        ((6, 21), (7, 22), "Рак"),
        ((7, 23), (8, 22), "Лев"),
        ((8, 23), (9, 22), "Дева"),
        ((9, 23), (10, 22), "Весы"),
        ((10, 23), (11, 21), "Скорпион"),
        ((11, 22), (12, 21), "Стрелец"),
        ((12, 22), (1, 19), "Козерог"),
        ((1, 20), (2, 18), "Водолей"),
        ((2, 19), (3, 20), "Рыбы"),
    ]
    for start, end, name in signs:
        if start <= d <= end:
            return name
    return "Козерог"


def build_natal_chart(
    profile: Profile,
    *,
    lat: float,
    lon: float,
    timezone: str,
) -> NatalChartData:
    accuracy, _ = calculate_profile_accuracy(profile)
    sun = _sun_sign(profile.birth_date)
    return NatalChartData(
        accuracy_tier=accuracy,
        sun_sign=sun,
        moon_sign=None,
        asc_sign=None,
        planets={"Sun": 0.0},
        birth_lat=lat,
        birth_lon=lon,
        timezone=timezone,
    )

