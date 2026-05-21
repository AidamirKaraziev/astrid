from datetime import date

from astra.astro.calculator import (
    build_transit_subject,
    kerykeion_available,
    natal_subject_from_chart,
)
from astra.astro.constants import (
    ASPECT_EN_TO_RU,
    NATAL_POINTS,
    PLANET_EN_TO_RU,
    TRANSIT_PLANETS,
)
from astra.astro.schemas import AstroContext, NatalChartData, TransitAspect
from astra.users.models import Profile

_MAX_ORB = 6.0
_TOP_ASPECTS = 5

_THEME_BY_PAIR: dict[tuple[str, str], str] = {
    ("Venus", "Moon"): "отношения, нежность, интуиция",
    ("Mars", "Sun"): "энергия, инициатива, смелость",
    ("Jupiter", "Sun"): "рост, оптимизм, возможности",
    ("Saturn", "Moon"): "ответственность, границы, зрелость",
    ("Mercury", "Mercury"): "общение, идеи, договорённости",
}


def _theme(transit: str, natal: str) -> str:
    return _THEME_BY_PAIR.get((transit, natal), "внутренние процессы и фокус дня")


def build_daily_context(
    profile: Profile,
    chart: NatalChartData,
    target: date,
) -> AstroContext:
    if not kerykeion_available():
        from astra.astro.simple import build_daily_context as simple_context

        return simple_context(profile, chart, target)

    from kerykeion import SynastryAspects

    lat = chart.birth_lat or 55.75
    lon = chart.birth_lon or 37.6
    tz = chart.timezone

    natal_subj = natal_subject_from_chart(profile, chart)
    transit_subj = build_transit_subject(target, lat=lat, lon=lon, timezone=tz)
    synastry = SynastryAspects(natal_subj, transit_subj)

    aspects: list[TransitAspect] = []
    for item in synastry.all_aspects:
        if item.p2_owner != "Transit":
            continue
        t_planet = item.p2_name
        n_planet = item.p1_name
        if t_planet not in TRANSIT_PLANETS or n_planet not in NATAL_POINTS:
            continue
        if float(item.orbit) > _MAX_ORB:
            continue
        aspects.append(
            TransitAspect(
                transit_planet=PLANET_EN_TO_RU.get(t_planet, t_planet),
                aspect=ASPECT_EN_TO_RU.get(item.aspect, item.aspect),
                natal_planet=PLANET_EN_TO_RU.get(n_planet, n_planet),
                orb_deg=round(float(item.orbit), 2),
                theme=_theme(t_planet, n_planet),
            ),
        )

    aspects.sort(key=lambda a: a.orb_deg)
    top = aspects[:_TOP_ASPECTS]

    if not top and chart.accuracy_tier <= 33:
        top = [
            TransitAspect(
                transit_planet="Солнце",
                aspect="фон дня",
                natal_planet=f"Солнце ({chart.sun_sign})",
                orb_deg=0.0,
                theme="общий солнечный ритм знака",
            ),
        ]

    return AstroContext(
        date=target,
        accuracy_tier=chart.accuracy_tier,
        natal={
            "sun": chart.sun_sign,
            "moon": chart.moon_sign,
            "asc": chart.asc_sign,
        },
        transits=top,
        moon_phase=None,
    )
