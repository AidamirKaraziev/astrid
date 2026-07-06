"""Детерминированные фичи натальной карты для промпта LLM.

Всё считается из FullNatalChart без обращения к kerykeion — чистые функции.
LLM получает готовые акценты (доминанты, стеллиумы, конфигурации) и не
вычисляет астрологию сам.
"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field

from astra.astro.schemas import ChartPoint, FullNatalChart, NatalAspect

_PLANETS = (
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
)

_MINOR_POINTS = {
    "Chiron",
    "Mean_Lilith",
    "True_North_Lunar_Node",
    "True_South_Lunar_Node",
}

_ANGULAR_ORB = 8.0
_STELLIUM_MIN = 3

# «Доминанта выражена», если вес стихии/креста ≥ 40% суммы
_DOMINANT_SHARE = 0.4


class Stellium(BaseModel):
    kind: str  # "sign" | "house"
    where: str  # знак по-русски или "N дом"
    planets: list[str]  # русские имена


class AspectConfiguration(BaseModel):
    kind: str  # "t_square" | "grand_trine"
    kind_ru: str
    planets: list[str]  # русские имена; для тау-квадрата вершина первой
    apex: str | None = None  # вершина тау-квадрата (по-русски)


class PointDigest(BaseModel):
    name_ru: str
    sign: str
    house: int | None = None
    retrograde: bool = False


class ChartFeatures(BaseModel):
    """Дайджест акцентов карты. Хранится в natal_reports.features."""

    schema_version: int = 1
    dominant_element: str | None = None  # None = сбалансировано
    dominant_modality: str | None = None
    element_balance: dict[str, float] = Field(default_factory=dict)
    modality_balance: dict[str, float] = Field(default_factory=dict)
    stellia: list[Stellium] = Field(default_factory=list)
    aspect_king: str | None = None  # самая аспектированная планета (по-русски)
    angular_planets: list[str] = Field(default_factory=list)  # у ASC/MC/DSC/IC
    retrograde_planets: list[str] = Field(default_factory=list)
    dignified_planets: dict[str, str] = Field(default_factory=dict)  # имя → достоинство
    configurations: list[AspectConfiguration] = Field(default_factory=list)
    hemisphere_emphasis: str | None = None  # напр. "верхняя (социальная) полусфера"
    north_node: PointDigest | None = None
    south_node: PointDigest | None = None
    chiron: PointDigest | None = None
    lilith: PointDigest | None = None
    final_dispositor: str | None = None  # v2: цепочки диспозиций


def _dominant(balance: dict[str, float]) -> str | None:
    if not balance:
        return None
    total = sum(balance.values())
    key, weight = max(balance.items(), key=lambda kv: kv[1])
    return key if total > 0 and weight / total >= _DOMINANT_SHARE else None


def _planet_points(chart: FullNatalChart) -> list[ChartPoint]:
    return [p for p in chart.points if p.name in _PLANETS]


def _find_stellia(chart: FullNatalChart) -> list[Stellium]:
    planets = _planet_points(chart)
    stellia: list[Stellium] = []
    by_sign: dict[str, list[ChartPoint]] = {}
    for p in planets:
        by_sign.setdefault(p.sign, []).append(p)
    for sign, members in by_sign.items():
        if len(members) >= _STELLIUM_MIN:
            stellia.append(
                Stellium(kind="sign", where=sign, planets=[p.name_ru for p in members])
            )
    if chart.has_time:
        by_house: dict[int, list[ChartPoint]] = {}
        for p in planets:
            if p.house is not None:
                by_house.setdefault(p.house, []).append(p)
        for house, members in sorted(by_house.items()):
            if len(members) >= _STELLIUM_MIN:
                stellia.append(
                    Stellium(
                        kind="house",
                        where=f"{house} дом",
                        planets=[p.name_ru for p in members],
                    )
                )
    return stellia


def _aspect_king(chart: FullNatalChart) -> str | None:
    counts: Counter[str] = Counter()
    for a in chart.aspects:
        for name in (a.p1, a.p2):
            if name in _PLANETS:
                counts[name] += 1
    if not counts:
        return None
    top_name, top_count = counts.most_common(1)[0]
    # при равенстве король не объявляется — акцент должен быть однозначным
    contenders = [n for n, c in counts.items() if c == top_count]
    if len(contenders) > 1:
        return None
    point = chart.point(top_name)
    return point.name_ru if point else None


def _circular_distance(a: float, b: float) -> float:
    diff = abs(a - b) % 360.0
    return min(diff, 360.0 - diff)


def _angular_planets(chart: FullNatalChart) -> list[str]:
    if not chart.has_time or chart.asc is None or chart.mc is None:
        return []
    angles = (
        chart.asc.lon,
        chart.mc.lon,
        (chart.asc.lon + 180.0) % 360.0,
        (chart.mc.lon + 180.0) % 360.0,
    )
    return [
        p.name_ru
        for p in _planet_points(chart)
        if any(_circular_distance(p.lon, angle) <= _ANGULAR_ORB for angle in angles)
    ]


def _aspect_pairs(chart: FullNatalChart, aspect_en: str) -> set[frozenset[str]]:
    return {
        frozenset((a.p1, a.p2))
        for a in chart.aspects
        if a.aspect_en == aspect_en and a.p1 in _PLANETS and a.p2 in _PLANETS
    }


def _name_ru(chart: FullNatalChart, name: str) -> str:
    point = chart.point(name)
    return point.name_ru if point else name


def _find_configurations(chart: FullNatalChart) -> list[AspectConfiguration]:
    squares = _aspect_pairs(chart, "square")
    oppositions = _aspect_pairs(chart, "opposition")
    trines = _aspect_pairs(chart, "trine")
    configs: list[AspectConfiguration] = []

    for opp in oppositions:
        a, b = tuple(opp)
        for apex in _PLANETS:
            if apex in opp:
                continue
            if frozenset((apex, a)) in squares and frozenset((apex, b)) in squares:
                configs.append(
                    AspectConfiguration(
                        kind="t_square",
                        kind_ru="тау-квадрат",
                        planets=[_name_ru(chart, apex), _name_ru(chart, a), _name_ru(chart, b)],
                        apex=_name_ru(chart, apex),
                    )
                )

    seen_trios: set[frozenset[str]] = set()
    for pair in trines:
        a, b = tuple(pair)
        for c in _PLANETS:
            if c in pair:
                continue
            trio = frozenset((a, b, c))
            if trio in seen_trios:
                continue
            if frozenset((a, c)) in trines and frozenset((b, c)) in trines:
                seen_trios.add(trio)
                configs.append(
                    AspectConfiguration(
                        kind="grand_trine",
                        kind_ru="большой трин",
                        planets=sorted(_name_ru(chart, n) for n in trio),
                    )
                )
    return configs


def _hemisphere_emphasis(chart: FullNatalChart) -> str | None:
    if not chart.has_time:
        return None
    houses = [p.house for p in _planet_points(chart) if p.house is not None]
    if len(houses) < 7:
        return None
    upper = sum(1 for h in houses if 7 <= h <= 12)
    east = sum(1 for h in houses if h in (10, 11, 12, 1, 2, 3))
    total = len(houses)
    parts: list[str] = []
    if upper / total >= 0.7:
        parts.append("верхняя (социальная) полусфера")
    elif (total - upper) / total >= 0.7:
        parts.append("нижняя (личная) полусфера")
    if east / total >= 0.7:
        parts.append("восточная полусфера (опора на себя)")
    elif (total - east) / total >= 0.7:
        parts.append("западная полусфера (реализация через других)")
    return ", ".join(parts) if parts else None


def _digest(chart: FullNatalChart, name: str) -> PointDigest | None:
    point = chart.point(name)
    if point is None:
        return None
    return PointDigest(
        name_ru=point.name_ru,
        sign=point.sign,
        house=point.house,
        retrograde=point.retrograde,
    )


def build_chart_features(chart: FullNatalChart) -> ChartFeatures:
    return ChartFeatures(
        dominant_element=_dominant(chart.element_balance),
        dominant_modality=_dominant(chart.modality_balance),
        element_balance=chart.element_balance,
        modality_balance=chart.modality_balance,
        stellia=_find_stellia(chart),
        aspect_king=_aspect_king(chart),
        angular_planets=_angular_planets(chart),
        retrograde_planets=[p.name_ru for p in _planet_points(chart) if p.retrograde],
        dignified_planets={
            p.name_ru: p.dignity for p in _planet_points(chart) if p.dignity
        },
        configurations=_find_configurations(chart),
        hemisphere_emphasis=_hemisphere_emphasis(chart),
        north_node=_digest(chart, "True_North_Lunar_Node"),
        south_node=_digest(chart, "True_South_Lunar_Node"),
        chiron=_digest(chart, "Chiron"),
        lilith=_digest(chart, "Mean_Lilith"),
    )
