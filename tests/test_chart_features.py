"""Тесты chart_features: синтетические карты + реальная фикстура 1990-06-15."""

from datetime import date, datetime

import pytest

from astra.astro.calculator import kerykeion_available
from astra.astro.chart_features import build_chart_features
from astra.astro.schemas import ChartPoint, FullNatalChart, NatalAspect


def _pt(
    name: str,
    name_ru: str,
    lon: float,
    sign: str,
    *,
    house: int | None = None,
    retro: bool = False,
    element: str | None = None,
    modality: str | None = None,
    dignity: str | None = None,
) -> ChartPoint:
    return ChartPoint(
        name=name,
        name_ru=name_ru,
        lon=lon,
        sign=sign,
        sign_deg=lon % 30.0,
        house=house,
        retrograde=retro,
        element=element,
        modality=modality,
        dignity=dignity,
    )


def _asp(p1: str, p1_ru: str, p2: str, p2_ru: str, aspect_en: str, orb: float) -> NatalAspect:
    ru = {
        "conjunction": "соединение",
        "sextile": "секстиль",
        "square": "квадрат",
        "trine": "трин",
        "opposition": "оппозиция",
    }[aspect_en]
    return NatalAspect(
        p1=p1, p1_ru=p1_ru, p2=p2, p2_ru=p2_ru, aspect=ru, aspect_en=aspect_en, orb_deg=orb
    )


def _chart(points: list[ChartPoint], aspects: list[NatalAspect], **kwargs) -> FullNatalChart:
    return FullNatalChart(has_time=False, points=points, aspects=aspects, **kwargs)


def test_sign_stellium_detected():
    points = [
        _pt("Sun", "Солнце", 95.0, "Рак"),
        _pt("Mercury", "Меркурий", 100.0, "Рак"),
        _pt("Venus", "Венера", 110.0, "Рак"),
        _pt("Moon", "Луна", 10.0, "Овен"),
    ]
    features = build_chart_features(_chart(points, []))
    assert len(features.stellia) == 1
    stellium = features.stellia[0]
    assert stellium.kind == "sign"
    assert stellium.where == "Рак"
    assert set(stellium.planets) == {"Солнце", "Меркурий", "Венера"}


def test_house_stellium_requires_time():
    points = [
        _pt("Sun", "Солнце", 95.0, "Рак", house=10),
        _pt("Mercury", "Меркурий", 130.0, "Лев", house=10),
        _pt("Venus", "Венера", 160.0, "Дева", house=10),
    ]
    chart = FullNatalChart(has_time=True, points=points, aspects=[])
    features = build_chart_features(chart)
    house_stellia = [s for s in features.stellia if s.kind == "house"]
    assert len(house_stellia) == 1
    assert house_stellia[0].where == "10 дом"


def test_t_square_detected_with_apex():
    points = [
        _pt("Sun", "Солнце", 10.0, "Овен"),
        _pt("Moon", "Луна", 190.0, "Весы"),
        _pt("Saturn", "Сатурн", 100.0, "Рак"),
    ]
    aspects = [
        _asp("Sun", "Солнце", "Moon", "Луна", "opposition", 0.5),
        _asp("Sun", "Солнце", "Saturn", "Сатурн", "square", 1.0),
        _asp("Moon", "Луна", "Saturn", "Сатурн", "square", 1.5),
    ]
    features = build_chart_features(_chart(points, aspects))
    t_squares = [c for c in features.configurations if c.kind == "t_square"]
    assert len(t_squares) == 1
    assert t_squares[0].apex == "Сатурн"
    assert t_squares[0].planets[0] == "Сатурн"


def test_grand_trine_detected_once():
    points = [
        _pt("Sun", "Солнце", 10.0, "Овен"),
        _pt("Jupiter", "Юпитер", 130.0, "Лев"),
        _pt("Moon", "Луна", 250.0, "Стрелец"),
    ]
    aspects = [
        _asp("Sun", "Солнце", "Jupiter", "Юпитер", "trine", 1.0),
        _asp("Jupiter", "Юпитер", "Moon", "Луна", "trine", 2.0),
        _asp("Sun", "Солнце", "Moon", "Луна", "trine", 3.0),
    ]
    features = build_chart_features(_chart(points, aspects))
    grand_trines = [c for c in features.configurations if c.kind == "grand_trine"]
    assert len(grand_trines) == 1
    assert grand_trines[0].planets == ["Луна", "Солнце", "Юпитер"]


def test_aspect_king_and_tie():
    points = [
        _pt("Sun", "Солнце", 10.0, "Овен"),
        _pt("Moon", "Луна", 100.0, "Рак"),
        _pt("Mars", "Марс", 190.0, "Весы"),
    ]
    aspects = [
        _asp("Sun", "Солнце", "Moon", "Луна", "square", 1.0),
        _asp("Sun", "Солнце", "Mars", "Марс", "opposition", 2.0),
    ]
    features = build_chart_features(_chart(points, aspects))
    assert features.aspect_king == "Солнце"

    # ничья — король не объявляется
    tie = [_asp("Sun", "Солнце", "Moon", "Луна", "square", 1.0)]
    assert build_chart_features(_chart(points, tie)).aspect_king is None


def test_dominant_element_threshold():
    balanced = _chart([], [], element_balance={"огонь": 4.0, "вода": 4.0, "воздух": 4.0, "земля": 3.5})
    assert build_chart_features(balanced).dominant_element is None

    dominant = _chart([], [], element_balance={"огонь": 8.0, "вода": 3.0, "воздух": 2.5, "земля": 2.0})
    assert build_chart_features(dominant).dominant_element == "огонь"


def test_angular_planets():
    asc = _pt("Ascendant", "Асцендент", 185.0, "Весы", house=1)
    mc = _pt("Medium_Coeli", "MC", 95.0, "Рак", house=10)
    points = [
        _pt("Saturn", "Сатурн", 190.0, "Весы", house=1),  # 5° от ASC
        _pt("Venus", "Венера", 8.0, "Овен", house=7),  # 3° от DSC (5°)
        _pt("Moon", "Луна", 240.0, "Стрелец", house=2),  # далеко
    ]
    chart = FullNatalChart(has_time=True, points=points, aspects=[], asc=asc, mc=mc)
    features = build_chart_features(chart)
    assert set(features.angular_planets) == {"Сатурн", "Венера"}


def test_minor_points_digest():
    points = [
        _pt("True_North_Lunar_Node", "Северный узел", 308.0, "Водолей", house=4),
        _pt("Chiron", "Хирон", 106.0, "Рак", house=10),
        _pt("Mean_Lilith", "Лилит", 234.0, "Скорпион", house=2),
    ]
    features = build_chart_features(_chart(points, []))
    assert features.north_node is not None and features.north_node.sign == "Водолей"
    assert features.chiron is not None and features.chiron.house == 10
    assert features.lilith is not None and features.lilith.name_ru == "Лилит"
    assert features.south_node is None


@pytest.mark.skipif(not kerykeion_available(), reason="kerykeion not installed")
def test_real_chart_features():
    from astra.astro.calculator import build_full_natal_chart

    chart = build_full_natal_chart(
        name="Тест",
        birth_date=date(1990, 6, 15),
        birth_time=datetime(1990, 6, 15, 14, 30),
        lat=55.7558,
        lon=37.6176,
        timezone="Europe/Moscow",
    )
    features = build_chart_features(chart)
    # Сатурн/Уран/Нептун в Козероге = стеллиум по знаку; в 4 доме тоже трое
    stellia_where = {s.where for s in features.stellia}
    assert "Козерог" in stellia_where
    assert "4 дом" in stellia_where
    assert set(features.retrograde_planets) == {"Сатурн", "Уран", "Нептун", "Плутон"}
    assert features.dignified_planets["Юпитер"] == "экзальтация"
    assert features.north_node is not None and features.north_node.sign == "Водолей"
    # кардинальный крест доминирует (7.5 из 15.5 < 40%? 48% — да)
    assert features.dominant_modality == "кардинальный"
    # roundtrip в JSONB
    from astra.astro.chart_features import ChartFeatures

    restored = ChartFeatures.model_validate(features.model_dump())
    assert restored == features
