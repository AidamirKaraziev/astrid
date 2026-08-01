"""Продукт «Почему я снова и снова обжигаюсь?»: петля, точка слома, ограждения."""

from datetime import date

import pytest

from astra.ask.pain_loop import (
    BREAK_POINT_BY_PLANET,
    LOOP_ALL_IN,
    LOOP_ESCAPE,
    LOOP_FIGHT,
    LOOP_MERGE,
    LOOP_PATIENCE,
    LOOP_RESCUE,
    LOOP_TAGLINE,
    LOOP_WAY_OUT,
    _pick_loop,
    compute,
    render_card,
)
from astra.ask.products import QUESTION_PAIN_LOOP, get_product
from astra.astro.calculator import kerykeion_available
from astra.astro.schemas import ChartPoint, FullNatalChart, HouseCusp, NatalAspect
from astra.llm.prompts.ask import pain_loop as product
from astra.users.gender import GENDER_FEMALE, GENDER_MALE

TODAY = date(2026, 8, 1)
BORN = date(1990, 3, 15)

pytestmark = pytest.mark.skipif(not kerykeion_available(), reason="kerykeion не установлен")


def _chart(
    *,
    dsc_sign: str = "Весы",
    venus_house: int = 5,
    moon_house: int = 4,
    mars_house: int = 1,
    chiron_house: int = 2,
    aspects: list[NatalAspect] | None = None,
    has_time: bool = True,
) -> FullNatalChart:
    """Синтетическая карта: проверяем правила, а не эфемериды."""
    points = [
        ChartPoint(name="Venus", name_ru="Венера", lon=45.0, sign="Телец", sign_deg=15.0, house=venus_house),
        ChartPoint(name="Moon", name_ru="Луна", lon=120.0, sign="Рак", sign_deg=12.0, house=moon_house),
        ChartPoint(name="Mars", name_ru="Марс", lon=10.0, sign="Овен", sign_deg=10.0, house=mars_house),
        ChartPoint(name="Saturn", name_ru="Сатурн", lon=300.0, sign="Козерог", sign_deg=5.0, house=10),
        ChartPoint(name="Uranus", name_ru="Уран", lon=250.0, sign="Стрелец", sign_deg=10.0, house=9),
        ChartPoint(name="Neptune", name_ru="Нептун", lon=280.0, sign="Козерог", sign_deg=8.0, house=10),
        ChartPoint(name="Pluto", name_ru="Плутон", lon=230.0, sign="Скорпион", sign_deg=15.0, house=8),
        ChartPoint(name="Chiron", name_ru="Хирон", lon=95.0, sign="Рак", sign_deg=5.0, house=chiron_house),
        ChartPoint(name="Jupiter", name_ru="Юпитер", lon=100.0, sign="Рак", sign_deg=10.0, house=4),
    ]
    houses = [HouseCusp(number=n, lon=float(n * 30), sign=dsc_sign) for n in range(1, 13)]
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


def _result(chart: FullNatalChart | None = None, *, leaves_first: bool = False):
    return compute(
        chart if chart is not None else _chart(),
        birth_date=BORN,
        calibration=leaves_first,
        today=TODAY,
    )


# ──────────────────────────────── петля ────────────────────────────────


def test_venus_saturn_gives_distance() -> None:
    """Венера под Сатурном — выбор недоступных."""
    chart = _chart(aspects=[_aspect("Venus", "Венера", "Saturn", "Сатурн")])
    assert _result(chart).loop == "Дистанция"


def test_venus_pluto_gives_all_in() -> None:
    chart = _chart(aspects=[_aspect("Venus", "Венера", "Pluto", "Плутон")])
    assert _result(chart).loop == LOOP_ALL_IN


def test_venus_uranus_gives_escape() -> None:
    chart = _chart(aspects=[_aspect("Venus", "Венера", "Uranus", "Уран")])
    assert _result(chart).loop == LOOP_ESCAPE


def test_mars_in_seventh_gives_fight() -> None:
    """Марс в 7 доме — партнёр как соперник."""
    chart = _chart(dsc_sign="Овен", mars_house=7)
    assert _result(chart).loop == LOOP_FIGHT


def test_venus_on_descendant_gives_merge() -> None:
    """Венера в оппозиции к асценденту — это Венера на десценденте."""
    chart = _chart(
        dsc_sign="Рыбы",
        aspects=[_aspect("Venus", "Венера", "Ascendant", "Асцендент", "оппозиция")],
    )
    result = _result(chart)
    assert result.factors.venus_on_descendant is True
    assert result.loop == LOOP_MERGE


def test_tie_is_resolved_by_fixed_priority() -> None:
    """Ничья решается приоритетом: карта одна — петля одна."""
    assert _pick_loop({LOOP_ESCAPE: 2.0, LOOP_ALL_IN: 2.0}) == LOOP_ALL_IN
    assert _pick_loop({}) == LOOP_PATIENCE


def test_same_chart_gives_same_loop() -> None:
    chart = _chart(aspects=[_aspect("Moon", "Луна", "Neptune", "Нептун")])
    assert _result(chart).loop == _result(chart).loop


def test_every_loop_has_a_tagline_and_a_way_out() -> None:
    assert set(LOOP_TAGLINE) == set(LOOP_WAY_OUT)
    for loop in LOOP_TAGLINE:
        assert LOOP_TAGLINE[loop] and LOOP_WAY_OUT[loop]


def test_loop_names_fit_on_the_card() -> None:
    """Карточка рисует героя в 190pt: длиннее девяти знаков уедет за край."""
    for loop in LOOP_TAGLINE:
        assert len(loop) <= 9, loop


# ─────────────────────────── точка слома и выход ───────────────────────────


def test_break_point_comes_from_the_leading_planet() -> None:
    chart = _chart(aspects=[_aspect("Venus", "Венера", "Uranus", "Уран")])
    assert _result(chart).break_point == BREAK_POINT_BY_PLANET["Uranus"]


def test_break_point_has_a_fallback_without_heavy_aspects() -> None:
    """Аспектов нет — точка слома всё равно есть, иначе блок ответа пустой."""
    result = _result(_chart())
    assert result.break_point
    assert result.way_out == LOOP_WAY_OUT[result.loop]


def test_no_birth_time_still_answers() -> None:
    result = _result(_chart(has_time=False, aspects=[_aspect("Moon", "Луна", "Saturn", "Сатурн")]))
    assert result.factors.dsc_sign is None
    assert result.loop in LOOP_TAGLINE


def test_calibration_lands_in_the_result() -> None:
    """Ответ «чаще ухожу я» переворачивает блок про роли, поэтому доезжает до схемы."""
    assert _result(leaves_first=True).leaves_first is True
    assert _result(leaves_first=False).leaves_first is False


# ─────────────────────────────── схема ответа ───────────────────────────────


def _answer(**overrides) -> product.PainLoopAnswer:
    payload = {
        "opening": "твоя карта показывает один и тот же поворот.",
        "loop_scene": "Л" * 200,
        "signs": ["объясняешь друзьям, почему он не пишет", "ждёшь звонка", "оправдываешь опоздания"],
        "break_scene": "Б" * 150,
        "roles": "Р" * 150,
        "way_out_text": "В" * 150,
        "safety": "С" * 200,
        "closing": "ты теперь этот поворот видишь.",
    }
    payload.update(overrides)
    return product.PainLoopAnswer.model_validate(payload)


def test_valid_answer_passes() -> None:
    assert product.validate(_answer(), product.expected_blocks(_result())) is None


def test_wrong_number_of_signs_is_rejected() -> None:
    assert product.validate(_answer(signs=["раз", "два"]), 3) == "signs_count_mismatch"


def test_missing_safety_block_is_rejected() -> None:
    """Без блока про безопасность продукт остаётся без выхода — это retry."""
    assert product.validate(_answer(safety="Если что — обращайся."), 3) == "safety_too_short"


@pytest.mark.parametrize(
    "text",
    [
        "Это классическая созависимость, " + "С" * 200,
        "Твой партнёр — нарцисс, " + "С" * 200,
        "Такие отношения токсичны, " + "С" * 200,
    ],
)
def test_diagnosis_is_rejected(text: str) -> None:
    """Продукт не ставит диагнозов: это не психотерапия."""
    assert (product.validate(_answer(roles=text), 3) or "").startswith("diagnosis:")


def test_banned_phrase_is_rejected() -> None:
    answer = _answer(loop_scene="Твоя энергетика притягивает таких. " + "Л" * 200)
    assert (product.validate(answer, 3) or "").startswith("banned_phrase")


def test_prompt_forbids_explaining_the_root() -> None:
    """Граница с вопросом «Как я сама рушу близость?» держится промптом."""
    assert "BOUNDARY" in product.SYSTEM_PROMPT
    assert "childhood" in product.SYSTEM_PROMPT
    assert "where the pattern came from" in product.SYSTEM_PROMPT


def test_prompt_forbids_blaming_the_reader() -> None:
    assert "Blaming the reader" in product.SYSTEM_PROMPT


# ───────────────────────────── рендер и имя ─────────────────────────────


def test_render_puts_the_name_in_twice() -> None:
    html_text = product.render_answer(_answer(), _result(), user_name="Аня")
    assert html_text.count("Аня,") == 2


def test_render_shows_computed_break_point_and_way_out() -> None:
    """Точку слома и выход считает Python — они в ответе всегда."""
    result = _result()
    html_text = product.render_answer(_answer(), result, user_name=None)
    assert result.break_point in html_text
    assert result.way_out in html_text


def test_name_never_reaches_the_model() -> None:
    message = product.build_user_message(_result(), user_name="Аня", gender=GENDER_FEMALE)
    assert "Аня" not in message


def test_reader_gender_reaches_the_model() -> None:
    """Своим родом человека PERSONA согласует весь текст — поле обязано доехать."""
    assert '"gender": "мужчина"' in product.build_user_message(_result(), gender=GENDER_MALE)


def test_render_capitalises_the_blocks_model_wrote_lowercase() -> None:
    """Правило «со строчной» касается только захода — остальное чинит код."""
    html_text = product.render_answer(
        _answer(loop_scene="всё начинается легко. " + "Л" * 200),
        _result(),
        user_name="Аня",
    )
    assert "Всё начинается легко" in html_text


def test_partner_gender_is_opposite_by_default() -> None:
    assert product._partner_gender(GENDER_FEMALE) == "мужской"
    assert product._partner_gender(GENDER_MALE) == "женский"
    assert product._partner_gender(None) == "нейтральный"


# ─────────────────────────── продукт целиком ───────────────────────────


def test_product_is_wired_into_the_registry() -> None:
    loaded = get_product(QUESTION_PAIN_LOOP)
    assert loaded is not None
    assert loaded.methodology_version == 1
    assert loaded.render_card is not None
    assert loaded.calibration_field == "leaves_first"


def test_teaser_greets_by_name() -> None:
    loaded = get_product(QUESTION_PAIN_LOOP)
    assert loaded is not None
    assert loaded.teaser_for("Аня").startswith("Аня, смотрю")
    assert loaded.teaser_for(None).startswith("Смотрю")


def test_card_renders() -> None:
    assert render_card(_result())[:4] == b"\x89PNG"


def test_card_caption_names_the_loop() -> None:
    result = _result()
    assert result.loop in product.card_caption(result)
