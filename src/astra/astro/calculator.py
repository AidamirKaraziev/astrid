from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from astra.astro.birth_time import birth_local_datetime
from astra.astro.schemas import ChartPoint, FullNatalChart, HouseCusp, NatalChartData
from astra.users.getters import calculate_profile_accuracy
from astra.users.models import Profile

try:
    from kerykeion import AstrologicalSubject

    _KERYKEION = True
except ImportError:
    AstrologicalSubject = None  # type: ignore[misc, assignment]
    _KERYKEION = False


def kerykeion_available() -> bool:
    return _KERYKEION


def _sign_ru(sign_en: str) -> str:
    from astra.astro.constants import SIGN_EN_TO_RU

    return SIGN_EN_TO_RU.get(sign_en, sign_en)


def _birth_local_datetime(profile: Profile, timezone: str) -> datetime:
    return birth_local_datetime(profile.birth_date, profile.birth_time, timezone)


def build_natal_chart(
    profile: Profile,
    *,
    lat: float,
    lon: float,
    timezone: str,
) -> NatalChartData:
    if not _KERYKEION:
        from astra.astro.simple import build_natal_chart as simple_build

        return simple_build(profile, lat=lat, lon=lon, timezone=timezone)

    accuracy, _ = calculate_profile_accuracy(profile)
    local_dt = _birth_local_datetime(profile, timezone)

    subject = AstrologicalSubject(
        profile.display_name,
        local_dt.year,
        local_dt.month,
        local_dt.day,
        local_dt.hour,
        local_dt.minute,
        lng=lon,
        lat=lat,
        tz_str=timezone,
    )

    planets: dict[str, float] = {}
    planet_signs: dict[str, str] = {}
    for name in ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn"):
        body = getattr(subject, name, None)
        if body is not None:
            planets[name.capitalize()] = float(body.abs_pos)
            planet_signs[name] = _sign_ru(body.sign)

    asc_sign: str | None = None
    if accuracy >= 66 and hasattr(subject, "first_house"):
        asc_sign = _sign_ru(subject.first_house.sign)

    moon_sign: str | None = _sign_ru(subject.moon.sign) if accuracy >= 66 else None

    return NatalChartData(
        accuracy_tier=accuracy,
        sun_sign=_sign_ru(subject.sun.sign),
        moon_sign=moon_sign,
        asc_sign=asc_sign,
        planet_signs=planet_signs,
        planets=planets,
        birth_lat=lat,
        birth_lon=lon,
        timezone=timezone,
    )


def build_natal_chart_for_birth(
    *,
    name: str,
    birth_date: date,
    birth_time: datetime | None,
    lat: float,
    lon: float,
    timezone: str,
    accuracy_tier: int,
) -> NatalChartData:
    """Натал для NatalProfile (не User.profile)."""
    if not _KERYKEION:
        from astra.astro.simple import NatalChartData as ChartData

        return ChartData(
            accuracy_tier=accuracy_tier,
            sun_sign="Водолей",
            moon_sign=None,
            asc_sign=None,
            birth_lat=lat,
            birth_lon=lon,
            timezone=timezone,
        )

    local_dt = birth_local_datetime(birth_date, birth_time, timezone)

    subject = AstrologicalSubject(
        name,
        local_dt.year,
        local_dt.month,
        local_dt.day,
        local_dt.hour,
        local_dt.minute,
        lng=lon,
        lat=lat,
        tz_str=timezone,
    )

    planets: dict[str, float] = {}
    planet_signs: dict[str, str] = {}
    for pname in ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn"):
        body = getattr(subject, pname, None)
        if body is not None:
            planets[pname.capitalize()] = float(body.abs_pos)
            planet_signs[pname] = _sign_ru(body.sign)

    asc_sign: str | None = None
    if accuracy_tier >= 66 and hasattr(subject, "first_house"):
        asc_sign = _sign_ru(subject.first_house.sign)
    moon_sign: str | None = _sign_ru(subject.moon.sign) if accuracy_tier >= 66 else None

    return NatalChartData(
        accuracy_tier=accuracy_tier,
        sun_sign=_sign_ru(subject.sun.sign),
        moon_sign=moon_sign,
        asc_sign=asc_sign,
        planet_signs=planet_signs,
        planets=planets,
        birth_lat=lat,
        birth_lon=lon,
        timezone=timezone,
    )


_FULL_CHART_POINTS = (
    "sun",
    "moon",
    "mercury",
    "venus",
    "mars",
    "jupiter",
    "saturn",
    "uranus",
    "neptune",
    "pluto",
    "chiron",
    "mean_lilith",
    "true_north_lunar_node",
    "true_south_lunar_node",
)

_HOUSE_ATTRS = (
    "first_house",
    "second_house",
    "third_house",
    "fourth_house",
    "fifth_house",
    "sixth_house",
    "seventh_house",
    "eighth_house",
    "ninth_house",
    "tenth_house",
    "eleventh_house",
    "twelfth_house",
)

# Веса для баланса стихий/крестов: светила ×2, личные ×1.5, социальные/высшие ×1.
_BALANCE_WEIGHTS: dict[str, float] = {
    "sun": 2.0,
    "moon": 2.0,
    "mercury": 1.5,
    "venus": 1.5,
    "mars": 1.5,
    "jupiter": 1.0,
    "saturn": 1.0,
    "uranus": 1.0,
    "neptune": 1.0,
    "pluto": 1.0,
}


def _make_subject(
    name: str,
    local_dt: datetime,
    *,
    lat: float,
    lon: float,
    timezone: str,
):
    return AstrologicalSubject(
        name,
        local_dt.year,
        local_dt.month,
        local_dt.day,
        local_dt.hour,
        local_dt.minute,
        lng=lon,
        lat=lat,
        tz_str=timezone,
        online=False,
    )


def _chart_point(name: str, body, *, house: int | None) -> ChartPoint:  # noqa: ANN001
    from astra.astro.constants import ELEMENT_EN_TO_RU, POINT_EN_TO_RU, QUALITY_EN_TO_RU
    from astra.astro.dignities import dignity_ru

    key = str(body.name)
    lon = float(body.abs_pos)
    return ChartPoint(
        name=key,
        name_ru=POINT_EN_TO_RU.get(key, key),
        lon=round(lon, 4),
        sign=_sign_ru(body.sign),
        sign_deg=round(lon % 30.0, 2),
        house=house,
        retrograde=bool(body.retrograde),
        element=ELEMENT_EN_TO_RU.get(str(body.element)),
        modality=QUALITY_EN_TO_RU.get(str(body.quality)),
        dignity=dignity_ru(name.capitalize() if name in _BALANCE_WEIGHTS else key, body.sign),
    )


def moon_sign_bounds(
    birth_date: date,
    *,
    lat: float,
    lon: float,
    timezone: str,
) -> tuple[str, str]:
    """Знаки Луны в начале и конце суток рождения (по-русски).

    Нужны, когда времени рождения нет: Луна проходит знак примерно за двое
    суток, поэтому честный ответ — назвать оба знака, а не выбрать один.
    """
    tz = ZoneInfo(timezone)
    start = datetime.combine(birth_date, time(0, 0), tzinfo=tz)
    end = datetime.combine(birth_date, time(23, 59), tzinfo=tz)
    moon_start = _make_subject("MoonStart", start, lat=lat, lon=lon, timezone=timezone).moon
    moon_end = _make_subject("MoonEnd", end, lat=lat, lon=lon, timezone=timezone).moon
    return _sign_ru(str(moon_start.sign)), _sign_ru(str(moon_end.sign))


def _moon_sign_uncertain(
    birth_date: date,
    *,
    lat: float,
    lon: float,
    timezone: str,
) -> bool:
    first, last = moon_sign_bounds(birth_date, lat=lat, lon=lon, timezone=timezone)
    return first != last


def build_full_natal_chart(
    *,
    name: str,
    birth_date: date,
    birth_time: datetime | None,
    lat: float,
    lon: float,
    timezone: str,
) -> FullNatalChart:
    """Полная карта для разбора натала: все точки, дома, аспекты, балансы.

    Без времени рождения дома/ASC/MC не публикуются (kerykeion их считает
    от полудня, но это фикция — честность гейтим здесь).
    """
    if not _KERYKEION:
        raise RuntimeError("kerykeion is not installed")

    from astra.astro.constants import HOUSE_NAME_TO_NUM, MOON_PHASE_EN_TO_RU
    from astra.astro.natal_aspects import compute_natal_aspects

    has_time = birth_time is not None
    local_dt = birth_local_datetime(birth_date, birth_time, timezone)

    subject = _make_subject(name, local_dt, lat=lat, lon=lon, timezone=timezone)

    points: list[ChartPoint] = []
    element_balance: dict[str, float] = {}
    modality_balance: dict[str, float] = {}
    for attr in _FULL_CHART_POINTS:
        body = getattr(subject, attr, None)
        if body is None:
            continue
        house = HOUSE_NAME_TO_NUM.get(str(body.house)) if has_time else None
        point = _chart_point(attr, body, house=house)
        points.append(point)
        weight = _BALANCE_WEIGHTS.get(attr)
        if weight and point.element and point.modality:
            element_balance[point.element] = element_balance.get(point.element, 0.0) + weight
            modality_balance[point.modality] = modality_balance.get(point.modality, 0.0) + weight

    asc: ChartPoint | None = None
    mc: ChartPoint | None = None
    houses: list[HouseCusp] | None = None
    if has_time:
        asc = _chart_point("ascendant", subject.ascendant, house=1)
        mc = _chart_point("medium_coeli", subject.medium_coeli, house=10)
        # ASC участвует в балансе с весом светила
        if asc.element and asc.modality:
            element_balance[asc.element] = element_balance.get(asc.element, 0.0) + 2.0
            modality_balance[asc.modality] = modality_balance.get(asc.modality, 0.0) + 2.0
        houses = [
            HouseCusp(
                number=idx,
                lon=round(float(cusp.abs_pos), 4),
                sign=_sign_ru(cusp.sign),
            )
            for idx, attr in enumerate(_HOUSE_ATTRS, start=1)
            if (cusp := getattr(subject, attr, None)) is not None
        ]

    moon_phase: str | None = None
    lunar = getattr(subject, "lunar_phase", None)
    if lunar is not None:
        phase_en = str(lunar.moon_phase_name)
        moon_phase = MOON_PHASE_EN_TO_RU.get(phase_en, phase_en)

    return FullNatalChart(
        has_time=has_time,
        moon_sign_uncertain=(
            False if has_time else _moon_sign_uncertain(birth_date, lat=lat, lon=lon, timezone=timezone)
        ),
        points=points,
        asc=asc,
        mc=mc,
        houses=houses,
        aspects=compute_natal_aspects(subject, has_time=has_time),
        element_balance={k: round(v, 1) for k, v in element_balance.items()},
        modality_balance={k: round(v, 1) for k, v in modality_balance.items()},
        moon_phase=moon_phase,
        birth_lat=lat,
        birth_lon=lon,
        timezone=timezone,
    )


def build_transit_subject(
    target: date,
    *,
    lat: float,
    lon: float,
    timezone: str,
):
    if not _KERYKEION:
        raise RuntimeError("kerykeion is not installed")
    return AstrologicalSubject(
        "Transit",
        target.year,
        target.month,
        target.day,
        12,
        0,
        lng=lon,
        lat=lat,
        tz_str=timezone,
    )


def natal_subject_from_chart(
    profile: Profile,
    chart: NatalChartData,
):
    if not _KERYKEION:
        raise RuntimeError("kerykeion is not installed")
    local_dt = _birth_local_datetime(profile, chart.timezone)
    return AstrologicalSubject(
        profile.display_name,
        local_dt.year,
        local_dt.month,
        local_dt.day,
        local_dt.hour,
        local_dt.minute,
        lng=chart.birth_lon or 37.6,
        lat=chart.birth_lat or 55.75,
        tz_str=chart.timezone,
    )
