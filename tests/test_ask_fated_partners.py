"""«Сколько судьбоносных партнёров?»: детерминированный расчёт двух чисел."""

from datetime import date, datetime

import pytest

from astra.ask.fated_partners import (
    METHODOLOGY_VERSION,
    _WINDOW_WEIGHTS,
    _max_past_for_age,
    _total_from_score,
    compute,
)
from astra.ask.windows import (
    TransitWindow,
    find_windows,
    merge_overlapping,
    split_by_today,
)
from astra.astro.calculator import build_full_natal_chart, kerykeion_available
from astra.astro.schemas import ChartPoint, FullNatalChart, HouseCusp, NatalAspect

TODAY = date(2026, 7, 28)

pytestmark = pytest.mark.skipif(not kerykeion_available(), reason="kerykeion не установлен")


def _chart(
    *,
    dsc_sign: str,
    venus_sign: str = "Телец",
    venus_modality: str = "фиксированный",
    venus_lon: float = 45.0,
    aspects: list[NatalAspect] | None = None,
    planets_in_seventh: int = 0,
    venus_retrograde: bool = False,
    has_time: bool = True,
) -> FullNatalChart:
    """Синтетическая карта: проверяем правила, а не эфемериды."""
    points = [
        ChartPoint(
            name="Venus",
            name_ru="Венера",
            lon=venus_lon,
            sign=venus_sign,
            sign_deg=15.0,
            house=5,
            retrograde=venus_retrograde,
            modality=venus_modality,
        ),
        ChartPoint(
            name="Saturn",
            name_ru="Сатурн",
            lon=200.0,
            sign="Весы",
            sign_deg=20.0,
            house=8,
            modality="кардинальный",
        ),
        ChartPoint(
            name="Uranus",
            name_ru="Уран",
            lon=250.0,
            sign="Стрелец",
            sign_deg=10.0,
            house=9,
            modality="мутабельный",
        ),
        ChartPoint(
            name="Jupiter",
            name_ru="Юпитер",
            lon=100.0,
            sign="Рак",
            sign_deg=10.0,
            house=3,
            modality="кардинальный",
        ),
        ChartPoint(
            name="Mars",
            name_ru="Марс",
            lon=300.0,
            sign="Водолей",
            sign_deg=1.0,
            house=11,
            modality="фиксированный",
        ),
        ChartPoint(
            name="Mercury",
            name_ru="Меркурий",
            lon=10.0,
            sign="Овен",
            sign_deg=10.0,
            house=1,
            modality="кардинальный",
        ),
    ]
    # В 7 дом сажаем личные планеты — только они идут в счёт.
    personal = [i for i, p in enumerate(points) if p.name in ("Venus", "Mars", "Mercury")]
    for index in personal[:planets_in_seventh]:
        points[index] = points[index].model_copy(update={"house": 7})

    houses = [HouseCusp(number=n, lon=float(n * 30), sign=dsc_sign) for n in range(1, 13)]
    return FullNatalChart(
        has_time=has_time,
        points=points,
        asc=ChartPoint(
            name="Ascendant",
            name_ru="Асцендент",
            lon=0.0,
            sign="Овен",
            sign_deg=0.0,
            house=1,
            modality="кардинальный",
        )
        if has_time
        else None,
        houses=houses if has_time else None,
        aspects=aspects or [],
    )


def _aspect(p1: str, p1_ru: str, p2: str, p2_ru: str, name: str = "квадрат") -> NatalAspect:
    return NatalAspect(
        p1=p1,
        p1_ru=p1_ru,
        p2=p2,
        p2_ru=p2_ru,
        aspect=name,
        aspect_en="square",
        orb_deg=2.0,
    )


# ─────────────────────────── правила счёта ───────────────────────────


def test_fixed_descendant_gives_fewer_partners_than_mutable() -> None:
    birth = date(1990, 3, 15)
    fixed = compute(
        _chart(dsc_sign="Телец"),
        birth_date=birth,
        calibration=False,
        today=TODAY,
    )
    mutable = compute(
        _chart(dsc_sign="Близнецы"),
        birth_date=birth,
        calibration=False,
        today=TODAY,
    )
    assert fixed.total < mutable.total
    assert mutable.factors.double_bodied_dsc is True


def test_saturn_on_venus_compresses_uranus_multiplies() -> None:
    birth = date(1990, 3, 15)
    saturn = compute(
        _chart(
            dsc_sign="Весы",
            aspects=[_aspect("Venus", "Венера", "Saturn", "Сатурн")],
        ),
        birth_date=birth,
        calibration=False,
        today=TODAY,
    )
    uranus = compute(
        _chart(
            dsc_sign="Весы",
            aspects=[_aspect("Venus", "Венера", "Uranus", "Уран")],
        ),
        birth_date=birth,
        calibration=False,
        today=TODAY,
    )
    assert saturn.factors.score < uranus.factors.score
    assert "Венера — квадрат — Сатурн" in saturn.factors.venus_aspects


def test_total_thresholds_are_monotonic() -> None:
    totals = [_total_from_score(score) for score in (-3.0, -1.0, 0.0, 1.0, 2.0, 4.0)]
    assert totals == sorted(totals)
    assert min(totals) == 1
    assert max(totals) == 4


def test_planets_in_seventh_are_collected() -> None:
    result = compute(
        _chart(dsc_sign="Весы", planets_in_seventh=2),
        birth_date=date(1990, 3, 15),
        calibration=False,
        today=TODAY,
    )
    assert len(result.factors.planets_in_seventh) == 2
    assert any("в 7 доме" in note for note in result.factors.notes)


# ─────────────────────────── прошлое и будущее ───────────────────────────


def test_numbers_always_add_up_and_stay_in_range() -> None:
    for dsc in ("Телец", "Близнецы", "Весы", "Рыбы", "Козерог"):
        for status in (True, False):
            result = compute(
                _chart(dsc_sign=dsc),
                birth_date=date(1988, 6, 1),
                calibration=status,
                today=TODAY,
            )
            assert result.past + result.future == result.total
            assert 1 <= result.total <= 4
            assert result.past >= 0 and result.future >= 0


def test_person_in_relationship_always_has_one_behind() -> None:
    result = compute(
        _chart(dsc_sign="Телец"),
        birth_date=date(2004, 6, 1),  # 22 года: окон в прошлом почти нет
        calibration=True,
        today=TODAY,
    )
    assert result.past >= 1


def test_young_person_cannot_have_many_behind() -> None:
    assert _max_past_for_age(21) == 1
    assert _max_past_for_age(27) == 2
    assert _max_past_for_age(34) == 3
    assert _max_past_for_age(45) == 4

    result = compute(
        _chart(dsc_sign="Рыбы"),
        birth_date=date(2005, 1, 10),
        calibration=False,
        today=TODAY,
    )
    assert result.age == 21
    assert result.past <= 1


def test_free_person_is_not_told_everything_is_behind() -> None:
    """Свободному человеку с открытым окном впереди всегда есть что обещать."""
    result = compute(
        _chart(dsc_sign="Весы"),
        birth_date=date(1975, 9, 20),
        calibration=False,
        today=TODAY,
    )
    assert result.future >= 1


# ─────────────────────────── воспроизводимость ───────────────────────────


def test_same_input_gives_same_answer() -> None:
    chart = build_full_natal_chart(
        name="X",
        birth_date=date(1990, 3, 15),
        birth_time=datetime(1990, 3, 15, 14, 30),
        lat=55.75,
        lon=37.61,
        timezone="Europe/Moscow",
    )
    first = compute(
        chart,
        birth_date=date(1990, 3, 15),
        calibration=False,
        today=TODAY,
    )
    second = compute(
        chart,
        birth_date=date(1990, 3, 15),
        calibration=False,
        today=TODAY,
    )
    assert (first.total, first.past, first.future) == (second.total, second.past, second.future)
    assert first.methodology_version == METHODOLOGY_VERSION


def test_real_chart_names_its_factors() -> None:
    birth = date(1990, 3, 15)
    chart = build_full_natal_chart(
        name="X",
        birth_date=birth,
        birth_time=datetime(1990, 3, 15, 14, 30),
        lat=55.75,
        lon=37.61,
        timezone="Europe/Moscow",
    )
    result = compute(chart, birth_date=birth, calibration=False, today=TODAY)

    assert result.factors.dsc_sign
    assert result.factors.ruler_seventh
    assert any("десцендент" in note for note in result.factors.notes)
    # Окна привязаны к точкам карты, а не выдуманы
    for window in result.windows_past + result.windows_future:
        assert window.target in {"десцендент", "Венера", "управитель 7 дома"}
        assert window.age >= 16


# ─────────────────────────── без времени рождения ───────────────────────────


def test_without_birth_time_houses_are_not_used() -> None:
    result = compute(
        _chart(dsc_sign="Телец", has_time=False),
        birth_date=date(1990, 3, 15),
        calibration=False,
        today=TODAY,
    )
    assert result.factors.has_time is False
    assert result.factors.dsc_sign is None
    assert result.factors.planets_in_seventh == []
    assert result.factors.north_node_house is None
    assert any("времени рождения нет" in note for note in result.factors.notes)
    assert 1 <= result.total <= 4


# ─────────────────────────── окна ───────────────────────────


def test_windows_are_found_and_ordered() -> None:
    windows = find_windows(
        {"десцендент": 315.6, "Венера": 309.1},
        weights=_WINDOW_WEIGHTS,
        birth_date=date(1990, 3, 15),
        today=TODAY,
    )
    assert windows
    assert windows == sorted(windows, key=lambda w: w.peak)
    assert all(w.transit in {"Сатурн", "Юпитер", "Уран"} for w in windows)


def test_overlapping_windows_are_one_story() -> None:
    def _window(peak: date, weight: float, transit: str) -> TransitWindow:
        return TransitWindow(
            start=peak,
            peak=peak,
            end=peak,
            transit=transit,
            target="десцендент",
            weight=weight,
            age=30,
        )

    merged = merge_overlapping(
        [
            _window(date(2021, 3, 1), 0.6, "Юпитер"),
            _window(date(2021, 6, 1), 1.0, "Сатурн"),
            _window(date(2033, 2, 1), 0.8, "Юпитер"),
        ],
    )
    assert len(merged) == 2
    assert merged[0].transit == "Сатурн"  # из пересекающихся оставили весомое


def test_split_by_today_counts_current_window_as_ahead() -> None:
    current = TransitWindow(
        start=date(2026, 6, 1),
        peak=date(2026, 8, 1),
        end=date(2026, 10, 31),
        transit="Сатурн",
        target="Венера",
        weight=0.7,
        age=36,
    )
    past, future = split_by_today([current], today=TODAY)
    assert past == []
    assert future == [current]
