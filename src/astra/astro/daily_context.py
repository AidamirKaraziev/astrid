"""Ежедневный контекст v2: транзиты к полной натальной карте.

Методика транзитной прогностики:
- дифференцированные орбы по транзитной планете (медленные — узкие);
- классификация: главный транзит дня (быстрая планета к личной точке,
  минимальная относительная точность) / фон (медленные) / транзитная Луна;
- активация натальных аспектов: транзит к точке «включает» её натальные связки;
- сфера дня — натальный дом задетой точки (при известном времени рождения).

Все вычисления детерминированные, LLM получает готовую классификацию.
"""

from __future__ import annotations

from datetime import date as date_type, datetime, time
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from astra.astro.constants import (
    ASPECT_EN_TO_RU,
    MOON_PHASE_EN_TO_RU,
    POINT_EN_TO_RU,
)
from astra.astro.schemas import FullNatalChart

# --- орбы по транзитной планете (градусы) ---
TRANSIT_ORB_LIMITS: dict[str, float] = {
    "Sun": 4.0,
    "Moon": 5.0,
    "Mercury": 4.0,
    "Venus": 4.0,
    "Mars": 3.5,
    "Jupiter": 2.5,
    "Saturn": 2.5,
    "Uranus": 1.5,
    "Neptune": 1.5,
    "Pluto": 1.5,
}

_FAST_PLANETS = ("Sun", "Mercury", "Venus", "Mars")  # Луна — отдельный блок
_SLOW_PLANETS = ("Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")

# личные точки натала — цели главного транзита
_PERSONAL_POINTS = {"Sun", "Moon", "Mercury", "Venus", "Mars", "Ascendant", "Medium_Coeli"}

_ASPECT_ANGLES: dict[str, float] = {
    "conjunction": 0.0,
    "sextile": 60.0,
    "square": 90.0,
    "trine": 120.0,
    "opposition": 180.0,
}

_ACTIVATION_MAX_ORB = 3.0  # натальный аспект считается «включаемым», если точен
_MAX_BACKGROUND = 2
_MAX_MOON_ASPECTS = 2
_MAX_ACTIVATED = 2

HOUSE_SPHERES: dict[int, str] = {
    1: "ты сам: самоподача и инициатива",
    2: "деньги и ресурсы",
    3: "общение, переписка, короткие дела",
    4: "дом и семья",
    5: "творчество, романтика, удовольствия",
    6: "рутина, работа-процесс и здоровье",
    7: "партнёрство и отношения",
    8: "общие ресурсы, кризисы, близость",
    9: "учёба, путешествия, смыслы",
    10: "карьера и репутация",
    11: "друзья, планы, сообщества",
    12: "отдых, уединение, внутренняя работа",
}


class DailyTransit(BaseModel):
    transit_planet: str  # по-русски
    transit_planet_key: str  # en-ключ
    aspect: str  # по-русски
    natal_point: str  # по-русски
    natal_point_key: str
    natal_sign: str
    natal_house: int | None = None
    orb_deg: float
    tightness: float  # орб / лимит, 0..1 — меньше = точнее


class MoonSignChange(BaseModel):
    to_sign: str
    approx_hour: int  # локальный час перехода (0–23)


class MoonContext(BaseModel):
    sign: str
    phase: str | None = None
    natal_house: int | None = None  # дом натала, по которому идёт транзитная Луна
    aspects: list[DailyTransit] = Field(default_factory=list)
    sign_change: MoonSignChange | None = None


class ActivatedNatalAspect(BaseModel):
    p1: str  # по-русски
    p2: str
    aspect: str
    orb_deg: float
    triggered_by: str  # транзитная планета (по-русски)


class SphereOfDay(BaseModel):
    house: int
    label: str


class DailyContextV2(BaseModel):
    schema_version: int = 2
    date: date_type
    accuracy_tier: int
    has_time: bool
    big_three: dict[str, str | None]
    main_transit: DailyTransit | None = None
    background: list[DailyTransit] = Field(default_factory=list)
    moon: MoonContext | None = None
    activated_natal_aspects: list[ActivatedNatalAspect] = Field(default_factory=list)
    sphere_of_day: SphereOfDay | None = None
    question_archetype_id: str | None = None


def _circular_distance(a: float, b: float) -> float:
    diff = abs(a - b) % 360.0
    return min(diff, 360.0 - diff)


def _match_aspect(t_lon: float, n_lon: float, limit: float) -> tuple[str, float] | None:
    """Ближайший мажорный аспект между долготами в пределах орба limit."""
    separation = _circular_distance(t_lon, n_lon)
    best: tuple[str, float] | None = None
    for name, angle in _ASPECT_ANGLES.items():
        orb = abs(separation - angle)
        if orb <= limit and (best is None or orb < best[1]):
            best = (name, orb)
    return best


def house_of_lon(lon: float, chart: FullNatalChart) -> int | None:
    """Номер натального дома, в который попадает долгота (по куспидам)."""
    if not chart.houses:
        return None
    cusps = sorted(chart.houses, key=lambda h: h.number)
    for i, cusp in enumerate(cusps):
        nxt = cusps[(i + 1) % 12]
        span = (nxt.lon - cusp.lon) % 360.0
        offset = (lon - cusp.lon) % 360.0
        if offset < span:
            return cusp.number
    return None


def _transit_positions(
    target: date_type,
    *,
    lat: float,
    lon: float,
    timezone: str,
    at: time = time(12, 0),
) -> tuple[dict[str, float], str | None, str]:
    """Долготы транзитных планет, фаза Луны (RU) и знак транзитной Луны (RU)."""
    from astra.astro.calculator import _make_subject, _sign_ru  # noqa: PLC2701

    local_dt = datetime.combine(target, at, tzinfo=ZoneInfo(timezone))
    subject = _make_subject("Transit", local_dt, lat=lat, lon=lon, timezone=timezone)

    positions: dict[str, float] = {}
    for attr in ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"):
        body = getattr(subject, attr, None)
        if body is not None:
            positions[str(body.name)] = float(body.abs_pos)

    phase: str | None = None
    lunar = getattr(subject, "lunar_phase", None)
    if lunar is not None:
        phase_en = str(lunar.moon_phase_name)
        phase = MOON_PHASE_EN_TO_RU.get(phase_en, phase_en)

    moon_sign = _sign_ru(str(subject.moon.sign))
    return positions, phase, moon_sign


def _moon_sign_change(
    target: date_type,
    moon_lon_noon: float,
    *,
    lat: float,
    lon: float,
    timezone: str,
) -> MoonSignChange | None:
    """Если Луна меняет знак в течение суток — знак и примерный локальный час."""
    from astra.astro.calculator import _make_subject, _sign_ru  # noqa: PLC2701

    tz = ZoneInfo(timezone)
    start = _make_subject(
        "MoonStart", datetime.combine(target, time(0, 0), tzinfo=tz),
        lat=lat, lon=lon, timezone=timezone,
    ).moon
    end = _make_subject(
        "MoonEnd", datetime.combine(target, time(23, 59), tzinfo=tz),
        lat=lat, lon=lon, timezone=timezone,
    ).moon
    if str(start.sign) == str(end.sign):
        return None

    # линейная интерполяция часа пересечения границы знака
    start_lon = float(start.abs_pos)
    end_lon = float(end.abs_pos)
    travelled = (end_lon - start_lon) % 360.0
    boundary = (int(start_lon // 30) + 1) * 30.0 % 360.0
    to_boundary = (boundary - start_lon) % 360.0
    if travelled <= 0:
        return None
    hour = int(round(24.0 * to_boundary / travelled))
    return MoonSignChange(to_sign=_sign_ru(str(end.sign)), approx_hour=min(hour, 23))


def _collect_transits(
    positions: dict[str, float],
    chart: FullNatalChart,
    planets: tuple[str, ...],
) -> list[DailyTransit]:
    targets: list[tuple[str, float, str, int | None]] = [
        (p.name, p.lon, p.sign, p.house) for p in chart.points
    ]
    if chart.asc is not None:
        targets.append(("Ascendant", chart.asc.lon, chart.asc.sign, 1))
    if chart.mc is not None:
        targets.append(("Medium_Coeli", chart.mc.lon, chart.mc.sign, 10))

    result: list[DailyTransit] = []
    for t_key in planets:
        t_lon = positions.get(t_key)
        limit = TRANSIT_ORB_LIMITS.get(t_key)
        if t_lon is None or limit is None:
            continue
        for n_key, n_lon, n_sign, n_house in targets:
            match = _match_aspect(t_lon, n_lon, limit)
            if match is None:
                continue
            aspect_en, orb = match
            result.append(
                DailyTransit(
                    transit_planet=POINT_EN_TO_RU.get(t_key, t_key),
                    transit_planet_key=t_key,
                    aspect=ASPECT_EN_TO_RU[aspect_en],
                    natal_point=POINT_EN_TO_RU.get(n_key, n_key),
                    natal_point_key=n_key,
                    natal_sign=n_sign,
                    natal_house=n_house,
                    orb_deg=round(orb, 2),
                    tightness=round(orb / limit, 3),
                ),
            )
    result.sort(key=lambda t: t.tightness)
    return result


def _activated_aspects(
    chart: FullNatalChart,
    natal_point_key: str,
    triggered_by: str,
) -> list[ActivatedNatalAspect]:
    activated = [
        ActivatedNatalAspect(
            p1=a.p1_ru,
            p2=a.p2_ru,
            aspect=a.aspect,
            orb_deg=a.orb_deg,
            triggered_by=triggered_by,
        )
        for a in chart.aspects
        if natal_point_key in (a.p1, a.p2) and a.orb_deg <= _ACTIVATION_MAX_ORB
    ]
    return activated[:_MAX_ACTIVATED]


def build_daily_context_v2(
    chart: FullNatalChart,
    target: date_type,
    *,
    accuracy_tier: int,
    question_archetype_id: str | None = None,
) -> DailyContextV2:
    lat = chart.birth_lat or 55.75
    lon = chart.birth_lon or 37.6
    tz = chart.timezone

    positions, moon_phase, moon_sign = _transit_positions(
        target, lat=lat, lon=lon, timezone=tz,
    )

    fast = _collect_transits(positions, chart, _FAST_PLANETS)
    slow = _collect_transits(positions, chart, _SLOW_PLANETS)
    moon_aspects = _collect_transits(positions, chart, ("Moon",))

    # главный транзит: точнейший быстрый к личной точке;
    # fallback — точнейший медленный к личной точке, затем любой быстрый
    def _personal(transits: list[DailyTransit]) -> list[DailyTransit]:
        return [t for t in transits if t.natal_point_key in _PERSONAL_POINTS]

    main = next(iter(_personal(fast)), None)
    if main is None:
        main = next(iter(_personal(slow)), None)
    if main is None:
        main = next(iter(fast), None) or next(iter(slow), None)

    background = [t for t in slow if t is not main][:_MAX_BACKGROUND]

    moon_lon = positions.get("Moon")
    moon_ctx = MoonContext(
        sign=moon_sign,
        phase=moon_phase,
        natal_house=house_of_lon(moon_lon, chart) if moon_lon is not None else None,
        aspects=[t for t in moon_aspects if t.natal_point_key in _PERSONAL_POINTS][:_MAX_MOON_ASPECTS],
        sign_change=(
            _moon_sign_change(target, moon_lon, lat=lat, lon=lon, timezone=tz)
            if moon_lon is not None
            else None
        ),
    )

    activated: list[ActivatedNatalAspect] = []
    if main is not None:
        activated = _activated_aspects(chart, main.natal_point_key, main.transit_planet)

    sphere: SphereOfDay | None = None
    if chart.has_time:
        sphere_house = main.natal_house if main is not None else None
        if sphere_house is None:
            sphere_house = moon_ctx.natal_house
        if sphere_house is not None:
            sphere = SphereOfDay(house=sphere_house, label=HOUSE_SPHERES[sphere_house])

    sun = chart.point("Sun")
    moon_natal = chart.point("Moon")
    return DailyContextV2(
        date=target,
        accuracy_tier=accuracy_tier,
        has_time=chart.has_time,
        big_three={
            "sun": sun.sign if sun else None,
            "moon": moon_natal.sign if moon_natal and (chart.has_time or not chart.moon_sign_uncertain) else None,
            "asc": chart.asc.sign if chart.asc else None,
        },
        main_transit=main,
        background=background,
        moon=moon_ctx,
        activated_natal_aspects=activated,
        sphere_of_day=sphere,
        question_archetype_id=question_archetype_id,
    )
