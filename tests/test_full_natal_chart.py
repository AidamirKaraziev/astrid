"""Тесты полной натальной карты: пиненая фикстура 1990-06-15 14:30 Москва.

Референс сверен с эфемеридами (astro-seek): при бампе kerykeion
любое расхождение в знаках/домах/ретро сломает тесты громко.
"""

from datetime import date, datetime

import pytest

from astra.astro.calculator import build_full_natal_chart, kerykeion_available
from astra.astro.dignities import dignity_for, dignity_ru

pytestmark = pytest.mark.skipif(not kerykeion_available(), reason="kerykeion not installed")

_BIRTH = {
    "name": "Тест",
    "birth_date": date(1990, 6, 15),
    "lat": 55.7558,
    "lon": 37.6176,
    "timezone": "Europe/Moscow",
}


@pytest.fixture(scope="module")
def chart():
    return build_full_natal_chart(
        birth_time=datetime(1990, 6, 15, 14, 30),
        **_BIRTH,
    )


@pytest.fixture(scope="module")
def chart_no_time():
    return build_full_natal_chart(birth_time=None, **_BIRTH)


def test_planet_signs_pinned(chart):
    expected = {
        "Sun": "Близнецы",
        "Moon": "Рыбы",
        "Mercury": "Близнецы",
        "Venus": "Телец",
        "Mars": "Овен",
        "Jupiter": "Рак",
        "Saturn": "Козерог",
        "Uranus": "Козерог",
        "Neptune": "Козерог",
        "Pluto": "Скорпион",
        "Chiron": "Рак",
        "Mean_Lilith": "Скорпион",
        "True_North_Lunar_Node": "Водолей",
        "True_South_Lunar_Node": "Лев",
    }
    actual = {p.name: p.sign for p in chart.points}
    assert actual == expected


def test_houses_and_angles_pinned(chart):
    assert chart.has_time
    assert chart.asc is not None and chart.asc.sign == "Весы"
    assert chart.mc is not None and chart.mc.sign == "Рак"
    assert chart.houses is not None and len(chart.houses) == 12
    assert [h.number for h in chart.houses] == list(range(1, 13))
    houses = {p.name: p.house for p in chart.points}
    assert houses["Sun"] == 9
    assert houses["Moon"] == 6
    assert houses["Saturn"] == 4
    assert houses["Pluto"] == 2


def test_retrogrades_pinned(chart):
    retro = {p.name for p in chart.points if p.retrograde}
    assert retro == {"Saturn", "Uranus", "Neptune", "Pluto"}


def test_dignities_pinned(chart):
    dignities = {p.name: p.dignity for p in chart.points if p.dignity}
    assert dignities == {
        "Mercury": "обитель",
        "Venus": "обитель",
        "Mars": "обитель",
        "Jupiter": "экзальтация",
        "Saturn": "обитель",
        "Pluto": "обитель",
    }


def test_aspects_sorted_and_filtered(chart):
    assert chart.aspects, "аспекты должны быть найдены"
    orbs = [a.orb_deg for a in chart.aspects]
    assert orbs == sorted(orbs)
    minors = {"Chiron", "Mean_Lilith", "True_North_Lunar_Node", "True_South_Lunar_Node"}
    assert not any(a.p1 in minors and a.p2 in minors for a in chart.aspects)
    for a in chart.aspects:
        assert a.aspect in {"соединение", "секстиль", "квадрат", "трин", "оппозиция"}
        assert a.orb_deg <= 8.0


def test_element_and_modality_balance(chart):
    # 4 стихии в сумме: 10 планет (2+2+1.5×3+1×5) + ASC(2) = 15.5
    assert sum(chart.element_balance.values()) == pytest.approx(15.5)
    assert sum(chart.modality_balance.values()) == pytest.approx(15.5)
    assert chart.modality_balance["кардинальный"] == pytest.approx(7.5)


def test_moon_phase(chart):
    assert chart.moon_phase == "последняя четверть"


def test_no_time_degrades_honestly(chart_no_time):
    assert not chart_no_time.has_time
    assert chart_no_time.asc is None
    assert chart_no_time.mc is None
    assert chart_no_time.houses is None
    assert all(p.house is None for p in chart_no_time.points)
    # без углов аспектов меньше, но они есть
    assert chart_no_time.aspects
    assert not any(a.p1 in ("Ascendant", "Medium_Coeli") for a in chart_no_time.aspects)
    assert not any(a.p2 in ("Ascendant", "Medium_Coeli") for a in chart_no_time.aspects)
    # Луна 1990-06-15 весь день в Рыбах — знак определён
    assert chart_no_time.moon_sign_uncertain is False


def test_full_chart_roundtrip_json(chart):
    from astra.astro.schemas import FullNatalChart

    restored = FullNatalChart.model_validate(chart.model_dump())
    assert restored == chart


def test_dignity_table():
    assert dignity_for("Sun", "Leo") == "domicile"
    assert dignity_for("Sun", "Aqu") == "detriment"
    assert dignity_for("Sun", "Ari") == "exaltation"
    assert dignity_for("Sun", "Lib") == "fall"
    assert dignity_for("Moon", "Tau") == "exaltation"
    assert dignity_for("Moon", "Sco") == "fall"
    assert dignity_for("Mercury", "Vir") == "domicile"  # обитель приоритетнее экзальтации
    assert dignity_for("Venus", "Ari") == "detriment"
    assert dignity_for("Mars", "Can") == "fall"
    assert dignity_for("Jupiter", "Gem") == "detriment"
    assert dignity_for("Saturn", "Ari") == "fall"
    assert dignity_for("Sun", "Gem") is None
    assert dignity_ru("Sun", "Leo") == "обитель"
    assert dignity_ru("Chiron", "Leo") is None
