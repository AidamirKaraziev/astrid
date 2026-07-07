"""Тесты daily-контекста v2: классификация транзитов, сфера, активация, деградация."""

from datetime import date, datetime

import pytest

from astra.astro.calculator import kerykeion_available
from astra.astro.daily_context import (
    TRANSIT_ORB_LIMITS,
    DailyContextV2,
    _match_aspect,
    house_of_lon,
)
from astra.astro.schemas import FullNatalChart, HouseCusp


class TestGeometry:
    def test_match_aspect_exact_and_orb(self):
        assert _match_aspect(10.0, 100.0, 4.0) == ("square", 0.0)
        name, orb = _match_aspect(10.0, 102.5, 4.0)
        assert name == "square" and orb == pytest.approx(2.5)
        assert _match_aspect(10.0, 105.0, 4.0) is None  # орб 5 > лимит 4
        # через 0° Овна
        name, orb = _match_aspect(358.0, 2.0, 5.0)
        assert name == "conjunction" and orb == pytest.approx(4.0)

    def test_house_of_lon(self):
        houses = [HouseCusp(number=i, lon=(i - 1) * 30.0, sign="—") for i in range(1, 13)]
        chart = FullNatalChart(has_time=True, points=[], houses=houses)
        assert house_of_lon(15.0, chart) == 1
        assert house_of_lon(290.0, chart) == 10
        assert house_of_lon(359.9, chart) == 12
        no_time = FullNatalChart(has_time=False, points=[])
        assert house_of_lon(15.0, no_time) is None

    def test_orb_limits_follow_methodology(self):
        # медленные — узкие орбы, светила — широкие
        assert TRANSIT_ORB_LIMITS["Pluto"] < TRANSIT_ORB_LIMITS["Saturn"]
        assert TRANSIT_ORB_LIMITS["Saturn"] < TRANSIT_ORB_LIMITS["Mars"]
        assert TRANSIT_ORB_LIMITS["Mars"] < TRANSIT_ORB_LIMITS["Moon"]


@pytest.mark.skipif(not kerykeion_available(), reason="kerykeion not installed")
class TestRealChart:
    """Пиненая фикстура: рождение 1990-06-15 14:30 Москва, транзиты на 2026-07-07."""

    @pytest.fixture(scope="class")
    def ctx(self) -> DailyContextV2:
        from astra.astro.calculator import build_full_natal_chart
        from astra.astro.daily_context import build_daily_context_v2

        chart = build_full_natal_chart(
            name="Тест",
            birth_date=date(1990, 6, 15),
            birth_time=datetime(1990, 6, 15, 14, 30),
            lat=55.7558,
            lon=37.6176,
            timezone="Europe/Moscow",
        )
        return build_daily_context_v2(chart, date(2026, 7, 7), accuracy_tier=100)

    def test_main_transit_pinned(self, ctx):
        assert ctx.main_transit is not None
        assert ctx.main_transit.transit_planet == "Марс"
        assert ctx.main_transit.aspect == "трин"
        assert ctx.main_transit.natal_point == "Асцендент"
        assert ctx.main_transit.orb_deg < 1.0
        # быстрая планета к личной точке
        assert ctx.main_transit.transit_planet_key in ("Sun", "Mercury", "Venus", "Mars")

    def test_background_is_slow_planets(self, ctx):
        assert 1 <= len(ctx.background) <= 2
        for t in ctx.background:
            assert t.transit_planet_key in ("Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")

    def test_moon_context(self, ctx):
        assert ctx.moon is not None
        assert ctx.moon.sign == "Овен"
        assert ctx.moon.phase == "последняя четверть"
        assert ctx.moon.natal_house == 7
        for asp in ctx.moon.aspects:
            assert asp.transit_planet_key == "Moon"

    def test_activated_natal_aspects_involve_hit_point(self, ctx):
        assert ctx.activated_natal_aspects
        for a in ctx.activated_natal_aspects:
            assert "Асцендент" in (a.p1, a.p2)
            assert a.orb_deg <= 3.0
            assert a.triggered_by == "Марс"

    def test_sphere_of_day_from_hit_point_house(self, ctx):
        assert ctx.sphere_of_day is not None
        assert ctx.sphere_of_day.house == 1  # ASC = 1 дом
        assert "самоподача" in ctx.sphere_of_day.label

    def test_big_three(self, ctx):
        assert ctx.big_three == {"sun": "Близнецы", "moon": "Рыбы", "asc": "Весы"}

    def test_jsonb_roundtrip(self, ctx):
        restored = DailyContextV2.model_validate(ctx.model_dump(mode="json"))
        assert restored == ctx
        assert restored.schema_version == 2


@pytest.mark.skipif(not kerykeion_available(), reason="kerykeion not installed")
class TestNoTimeDegradation:
    @pytest.fixture(scope="class")
    def ctx(self) -> DailyContextV2:
        from astra.astro.calculator import build_full_natal_chart
        from astra.astro.daily_context import build_daily_context_v2

        chart = build_full_natal_chart(
            name="Тест",
            birth_date=date(1990, 6, 15),
            birth_time=None,
            lat=55.7558,
            lon=37.6176,
            timezone="Europe/Moscow",
        )
        return build_daily_context_v2(chart, date(2026, 7, 7), accuracy_tier=33)

    def test_no_houses_no_sphere(self, ctx):
        assert not ctx.has_time
        assert ctx.sphere_of_day is None
        assert ctx.moon is not None and ctx.moon.natal_house is None
        assert ctx.big_three["asc"] is None

    def test_main_transit_never_to_angles(self, ctx):
        assert ctx.main_transit is not None
        assert ctx.main_transit.natal_point_key not in ("Ascendant", "Medium_Coeli")
        assert ctx.main_transit.natal_house is None

    def test_still_has_transits(self, ctx):
        # без времени всё равно есть главный транзит и Луна — контекст не пустой
        assert ctx.moon is not None and ctx.moon.sign
        assert ctx.moon.phase is not None
