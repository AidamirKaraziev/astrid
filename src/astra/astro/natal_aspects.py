"""Натальные аспекты через kerykeion.NatalAspects с явными орбами.

Дефолтные орбы kerykeion не подходят (квадрат 5°), поэтому active_aspects
передаются всегда. Правила орбов:
- соединение/оппозиция 8°, трин/квадрат 7°, секстиль 5°;
- если ни одна из точек не светило (Солнце/Луна) — орб на 1° жёстче;
- пары «минор–минор» (Хирон/Лилит/узлы между собой) отбрасываются.
"""

from __future__ import annotations

from astra.astro.constants import ASPECT_EN_TO_RU, POINT_EN_TO_RU
from astra.astro.schemas import NatalAspect

try:
    from kerykeion import NatalAspects as KrNatalAspects

    _KERYKEION = True
except ImportError:
    KrNatalAspects = None  # type: ignore[misc, assignment]
    _KERYKEION = False

_LUMINARIES = {"Sun", "Moon"}

_MINOR_POINTS = {
    "Chiron",
    "Mean_Lilith",
    "True_North_Lunar_Node",
    "True_South_Lunar_Node",
}

_MAX_ORBS: dict[str, float] = {
    "conjunction": 8.0,
    "opposition": 8.0,
    "trine": 7.0,
    "square": 7.0,
    "sextile": 5.0,
}

_ACTIVE_ASPECTS = [{"name": name, "orb": orb} for name, orb in _MAX_ORBS.items()]

_BASE_POINTS = [
    "Sun",
    "Moon",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
    "Uranus",
    "Neptune",
    "Pluto",
    "Chiron",
    "True_North_Lunar_Node",
]

_ANGLE_POINTS = ["Ascendant", "Medium_Coeli"]


def _orb_limit(aspect_en: str, p1: str, p2: str) -> float:
    limit = _MAX_ORBS[aspect_en]
    if not ({p1, p2} & _LUMINARIES):
        limit -= 1.0
    return limit


def compute_natal_aspects(subject, *, has_time: bool) -> list[NatalAspect]:  # noqa: ANN001
    """Мажорные аспекты внутри карты, отсортированные по орбу (точные первыми)."""
    if not _KERYKEION:
        return []

    active_points = list(_BASE_POINTS)
    if has_time:
        active_points += _ANGLE_POINTS

    kr = KrNatalAspects(
        subject,
        active_points=active_points,
        active_aspects=_ACTIVE_ASPECTS,
    )

    result: list[NatalAspect] = []
    for asp in kr.relevant_aspects:
        aspect_en = asp.aspect
        if aspect_en not in _MAX_ORBS:
            continue
        p1, p2 = asp.p1_name, asp.p2_name
        if p1 in _MINOR_POINTS and p2 in _MINOR_POINTS:
            continue
        orb = abs(float(asp.orbit))
        if orb > _orb_limit(aspect_en, p1, p2):
            continue
        result.append(
            NatalAspect(
                p1=p1,
                p1_ru=POINT_EN_TO_RU.get(p1, p1),
                p2=p2,
                p2_ru=POINT_EN_TO_RU.get(p2, p2),
                aspect=ASPECT_EN_TO_RU[aspect_en],
                aspect_en=aspect_en,
                orb_deg=round(orb, 2),
            )
        )

    result.sort(key=lambda a: a.orb_deg)
    return result
