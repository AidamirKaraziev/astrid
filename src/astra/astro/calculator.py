from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from astra.astro.schemas import NatalChartData
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
    tz = ZoneInfo(timezone)
    if profile.birth_time is not None:
        bt = profile.birth_time
        if bt.tzinfo is None:
            return bt.replace(tzinfo=tz)
        return bt.astimezone(tz)
    return datetime.combine(profile.birth_date, time(12, 0), tzinfo=tz)


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
    for name in ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn"):
        body = getattr(subject, name, None)
        if body is not None:
            planets[name.capitalize()] = float(body.abs_pos)

    asc_sign: str | None = None
    if accuracy >= 66 and hasattr(subject, "first_house"):
        asc_sign = _sign_ru(subject.first_house.sign)

    moon_sign: str | None = _sign_ru(subject.moon.sign) if accuracy >= 66 else None

    return NatalChartData(
        accuracy_tier=accuracy,
        sun_sign=_sign_ru(subject.sun.sign),
        moon_sign=moon_sign,
        asc_sign=asc_sign,
        planets=planets,
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
