"""Продукт «Будут ли у меня дети?»: расчёт темы, окна и правило «никогда нет»."""

from datetime import date, datetime

import pytest

from astra.ask.children import (
    MAX_PARENTING_AGE,
    THEME_EFFORT,
    THEME_LATE,
    compute,
    render_card,
)
from astra.ask.products import SPECS, QUESTION_CHILDREN, get_product
from astra.ask.windows import TransitWindow
from astra.astro.calculator import build_full_natal_chart, kerykeion_available
from astra.astro.schemas import ChartPoint, FullNatalChart, HouseCusp, NatalAspect
from astra.ask.windows import window_period
from astra.llm.prompts.ask import children as product

TODAY = date(2026, 7, 28)

pytestmark = pytest.mark.skipif(not kerykeion_available(), reason="kerykeion не установлен")


def _chart(
    *,
    fifth_sign: str = "Весы",
    aspects: list[NatalAspect] | None = None,
    saturn_in_fifth: bool = False,
    has_time: bool = True,
) -> FullNatalChart:
    points = [
        ChartPoint(
            name="Moon",
            name_ru="Луна",
            lon=120.0,
            sign="Лев",
            sign_deg=10.0,
            house=4,
            modality="фиксированный",
        ),
        ChartPoint(
            name="Jupiter",
            name_ru="Юпитер",
            lon=200.0,
            sign="Весы",
            sign_deg=20.0,
            house=7,
            modality="кардинальный",
        ),
        ChartPoint(
            name="Venus",
            name_ru="Венера",
            lon=45.0,
            sign="Телец",
            sign_deg=15.0,
            house=2,
            modality="фиксированный",
        ),
        ChartPoint(
            name="Saturn",
            name_ru="Сатурн",
            lon=300.0,
            sign="Водолей",
            sign_deg=5.0,
            house=5 if saturn_in_fifth else 10,
            modality="фиксированный",
        ),
        ChartPoint(
            name="Pluto",
            name_ru="Плутон",
            lon=250.0,
            sign="Стрелец",
            sign_deg=5.0,
            house=9,
            modality="мутабельный",
        ),
    ]
    houses = [HouseCusp(number=n, lon=float(n * 30), sign=fifth_sign) for n in range(1, 13)]
    return FullNatalChart(
        has_time=has_time,
        points=points,
        houses=houses if has_time else None,
        aspects=aspects or [],
    )


def _aspect(p1: str, p1_ru: str, p2: str, p2_ru: str, name: str = "квадрат") -> NatalAspect:
    return NatalAspect(
        p1=p1, p1_ru=p1_ru, p2=p2, p2_ru=p2_ru, aspect=name, aspect_en="square", orb_deg=2.0,
    )


def _result(**kwargs):
    chart = kwargs.pop("chart", None) or _chart()
    return compute(
        chart,
        birth_date=kwargs.pop("birth_date", date(1990, 3, 15)),
        calibration=kwargs.pop("has_children", False),
        today=TODAY,
    )


# ─────────────────────────── правило «никогда нет» ───────────────────────────


def test_chart_always_shows_at_least_one_child() -> None:
    """Ноль не отдаём ни при каком раскладе: карта не видит фертильность."""
    for sign in ("Близнецы", "Лев", "Дева", "Рак", "Козерог"):
        result = _result(
            chart=_chart(
                fifth_sign=sign,
                saturn_in_fifth=True,
                aspects=[
                    _aspect("Moon", "Луна", "Saturn", "Сатурн"),
                    _aspect("Moon", "Луна", "Pluto", "Плутон"),
                ],
            ),
        )
        assert result.count_hint >= 1
        assert result.count_hint <= 3


def test_denial_in_llm_answer_is_rejected() -> None:
    answer = _answer()
    answer.what_to_know = "Скорее всего, детей не будет — так показывает карта. " * 3
    assert product.validate(answer, expected_windows=len(_result().windows)) == "denial_not_allowed"


# ─────────────────────────── сценарий темы ───────────────────────────


def test_saturn_in_fifth_makes_theme_late() -> None:
    result = _result(chart=_chart(saturn_in_fifth=True))
    assert result.theme == THEME_LATE


def test_saturn_plus_pluto_makes_theme_through_effort() -> None:
    result = _result(
        chart=_chart(
            saturn_in_fifth=True,
            aspects=[_aspect("Moon", "Луна", "Pluto", "Плутон")],
        ),
    )
    assert result.theme == THEME_EFFORT


def test_fertile_sign_gives_more_children_than_barren() -> None:
    fertile = _result(chart=_chart(fifth_sign="Рак"))
    barren = _result(chart=_chart(fifth_sign="Дева"))
    assert fertile.count_hint >= barren.count_hint
    assert fertile.factors.fifth_fertility == "плодородный"
    assert barren.factors.fifth_fertility == "сухой"


# ─────────────────────────── окна ───────────────────────────


def test_windows_are_ranked_and_capped() -> None:
    result = _result()
    assert len(result.windows) <= 3
    assert result.best_window is not None
    assert result.best_window.weight == max(w.weight for w in result.windows)
    assert result.windows == sorted(result.windows, key=lambda w: w.peak)
    assert all(w.age <= MAX_PARENTING_AGE for w in result.windows)


def test_after_parenting_age_no_windows_are_promised() -> None:
    result = _result(birth_date=date(1970, 5, 5))  # 56 лет
    assert result.parenting_age_passed is True
    assert result.windows == []
    assert result.best_window is None


def test_window_period_reads_as_years() -> None:
    same_year = TransitWindow(
        start=date(2029, 3, 1),
        peak=date(2029, 5, 1),
        end=date(2029, 8, 31),
        transit="Юпитер",
        target="5 дом",
        weight=1.0,
        age=39,
    )
    crossing = same_year.model_copy(update={"end": date(2030, 2, 28)})
    assert window_period(same_year) == "2029"
    assert window_period(crossing) == "2029–2030"


def test_without_birth_time_falls_back_to_moon() -> None:
    result = _result(chart=_chart(has_time=False))
    assert result.factors.has_time is False
    assert result.factors.fifth_sign is None
    assert result.count_hint >= 1


def test_real_chart_names_its_factors() -> None:
    birth = date(1992, 8, 20)
    chart = build_full_natal_chart(
        name="X",
        birth_date=birth,
        birth_time=datetime(1992, 8, 20, 9, 15),
        lat=55.75,
        lon=37.61,
        timezone="Europe/Moscow",
    )
    result = compute(chart, birth_date=birth, calibration=False, today=TODAY)
    assert result.factors.notes
    assert any("5 дом" in note or "Луна" in note for note in result.factors.notes)


# ─────────────────────────── ответ и карточка ───────────────────────────


def _answer(windows: int = 3) -> product.ChildrenAnswer:
    return product.ChildrenAnswer(
        opening="Твоя карта говорит об этой теме спокойно и довольно ясно.",
        theme_line="Тема детей у тебя не ранняя, но и не закрытая",
        count_line="Карта показывает столько, сколько выдерживает твой пятый дом. " * 2,
        windows=[
            product.WindowMeaning(
                meaning="Юпитер подходит к твоей Луне — период, когда тема становится живой.",
            )
            for _ in range(windows)
        ],
        role_of_children="Дети для тебя — продолжение дела, а не смысл вместо него. " * 2,
        what_to_know="Ты склонна откладывать эту тему до идеальных условий. " * 2,
        closing="Смотри на ближайшее окно спокойно.",
    )


def test_rendered_answer_has_periods_from_code_and_medical_note() -> None:
    result = _result()
    html = product.render_answer(_answer(len(result.windows)), result)
    assert "Лучшие окна" in html
    assert "самое сильное" in html
    assert str(result.windows[0].peak.year) in html
    assert "Вопросы фертильности — к врачу" in html


def test_validate_requires_meaning_per_window() -> None:
    result = _result()
    assert product.validate(_answer(len(result.windows)), len(result.windows)) is None
    assert product.validate(_answer(1), len(result.windows)) == "windows_count_mismatch"


def test_card_caption_and_png() -> None:
    result = _result()
    caption = product.card_caption(result)
    assert "Карта показывает" in caption
    assert "Лучшее окно" in caption
    png = render_card(result)
    assert png.startswith(b"\x89PNG")


# ─────────────────────────── реестр продуктов ───────────────────────────


def test_children_product_is_registered_with_its_own_calibration() -> None:
    product_entry = get_product(QUESTION_CHILDREN)
    assert product_entry is not None
    assert product_entry.calibration_field == "has_children"
    assert "дети" in product_entry.calibration_text.lower()
    assert product_entry.validate_expected(_result()) == len(_result().windows)


def test_every_registered_product_has_full_contract() -> None:
    """Каждый продукт из реестра грузится и выполняет общий контракт."""
    for key in SPECS:
        entry = get_product(key)
        assert entry is not None, key
        assert entry.key == key
        assert entry.prompt.SYSTEM_PROMPT
        assert entry.invoice_title and entry.teaser
        assert entry.calibration_yes and entry.calibration_no
        assert callable(entry.compute)
        assert isinstance(entry.methodology_version, int)
        assert callable(entry.prompt.expected_blocks)
