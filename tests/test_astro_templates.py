from datetime import date
from types import SimpleNamespace

from astra.astro.schemas import AstroContext, NatalChartData, TransitAspect
from astra.astro.simple import build_daily_context
from astra.astro.templates import body_from_context


def test_simple_build_daily_context() -> None:
    chart = NatalChartData(
        accuracy_tier=33,
        sun_sign="Рыбы",
        timezone="Europe/Moscow",
    )
    ctx = build_daily_context(SimpleNamespace(), chart, date(2026, 5, 18))
    assert ctx.date == date(2026, 5, 18)
    assert ctx.transits


def test_body_from_transit_aspect() -> None:
    ctx = AstroContext(
        date=date(2026, 5, 18),
        accuracy_tier=100,
        natal={"sun": "Рыбы", "moon": "Рак", "asc": "Весы"},
        transits=[
            TransitAspect(
                transit_planet="Венера",
                aspect="трин",
                natal_planet="Луна",
                orb_deg=1.2,
                theme="нежность",
            ),
        ],
    )
    body = body_from_context(ctx)
    assert "Венера" in body
    assert "трин" in body
