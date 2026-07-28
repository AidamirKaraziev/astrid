"""Продукт «Какими будут отношения с детьми?»: тип родителя и категоричный тон."""

from datetime import date, datetime

import pytest

from astra.ask.kids_bond import (
    ARCHETYPE_FRIEND,
    ARCHETYPE_GUARD,
    ARCHETYPE_MENTOR,
    ARCHETYPE_SUPPORT,
    ARCHETYPE_TAGLINE,
    _pick_archetype,
    compute,
    render_card,
)
from astra.ask.products import QUESTION_KIDS_BOND, get_product
from astra.astro.calculator import build_full_natal_chart, kerykeion_available
from astra.astro.schemas import ChartPoint, FullNatalChart, HouseCusp, NatalAspect
from astra.llm.prompts.ask import kids_bond as product

TODAY = date(2026, 7, 28)

pytestmark = pytest.mark.skipif(not kerykeion_available(), reason="kerykeion не установлен")


def _chart(
    *,
    fifth_sign: str = "Весы",
    moon_sign: str = "Рак",
    moon_house: int = 4,
    mercury_sign: str = "Близнецы",
    saturn_house: int = 10,
    aspects: list[NatalAspect] | None = None,
    has_time: bool = True,
) -> FullNatalChart:
    points = [
        ChartPoint(name="Moon", name_ru="Луна", lon=120.0, sign=moon_sign, sign_deg=10.0, house=moon_house),
        ChartPoint(name="Mercury", name_ru="Меркурий", lon=70.0, sign=mercury_sign, sign_deg=5.0, house=3),
        ChartPoint(name="Venus", name_ru="Венера", lon=200.0, sign="Весы", sign_deg=20.0, house=7),
        ChartPoint(name="Saturn", name_ru="Сатурн", lon=300.0, sign="Козерог", sign_deg=5.0, house=saturn_house),
        ChartPoint(name="Uranus", name_ru="Уран", lon=250.0, sign="Стрелец", sign_deg=10.0, house=9),
        ChartPoint(name="Pluto", name_ru="Плутон", lon=230.0, sign="Скорпион", sign_deg=15.0, house=8),
    ]
    houses = [HouseCusp(number=n, lon=float(n * 30), sign=fifth_sign) for n in range(1, 13)]
    return FullNatalChart(
        has_time=has_time,
        points=points,
        houses=houses if has_time else None,
        aspects=aspects or [],
    )


def _aspect(p2: str, p2_ru: str, name: str = "квадрат") -> NatalAspect:
    return NatalAspect(
        p1="Moon", p1_ru="Луна", p2=p2, p2_ru=p2_ru, aspect=name, aspect_en="square", orb_deg=2.0,
    )


def _result(**kwargs):
    chart = kwargs.pop("chart", None) or _chart()
    return compute(
        chart,
        birth_date=kwargs.pop("birth_date", date(1990, 3, 15)),
        calibration=kwargs.pop("has_children", True),
        today=TODAY,
    )


# ─────────────────────────── тип родителя ───────────────────────────


def test_moon_saturn_gives_support_type() -> None:
    result = _result(chart=_chart(aspects=[_aspect("Saturn", "Сатурн")]))
    assert result.archetype == ARCHETYPE_SUPPORT
    assert result.factors.moon_parenting_model == "закрытая, контролирующая близость"


def test_moon_uranus_gives_friend_model() -> None:
    result = _result(chart=_chart(fifth_sign="Водолей", aspects=[_aspect("Uranus", "Уран")]))
    assert result.factors.moon_parenting_model == "непредсказуемая близость, на дистанции"
    assert result.factors.scores.get(ARCHETYPE_FRIEND, 0) > 0


def test_water_fifth_house_leans_to_guard_or_muse() -> None:
    result = _result(chart=_chart(fifth_sign="Скорпион"))
    assert result.factors.scores.get(ARCHETYPE_GUARD, 0) > 0


def test_air_mercury_adds_mentor() -> None:
    result = _result(chart=_chart(mercury_sign="Близнецы"))
    assert result.factors.mercury_talk_style == "быстрый, объясняющий, много слов"
    assert result.factors.scores.get(ARCHETYPE_MENTOR, 0) > 0


def test_tie_is_resolved_by_fixed_priority_not_by_chance() -> None:
    """Ничья не должна «плавать» между прогонами — иначе тип нестабилен."""
    tie = {ARCHETYPE_FRIEND: 2.0, ARCHETYPE_SUPPORT: 2.0, ARCHETYPE_MENTOR: 2.0}
    assert _pick_archetype(tie) == ARCHETYPE_SUPPORT
    assert _pick_archetype({}) == ARCHETYPE_SUPPORT


def test_every_archetype_has_a_tagline_for_the_card() -> None:
    for archetype in ARCHETYPE_TAGLINE:
        assert ARCHETYPE_TAGLINE[archetype]


def test_same_chart_gives_same_type() -> None:
    birth = date(1993, 6, 12)
    chart = build_full_natal_chart(
        name="X",
        birth_date=birth,
        birth_time=datetime(1993, 6, 12, 8, 40),
        lat=55.75,
        lon=37.61,
        timezone="Europe/Moscow",
    )
    first = compute(chart, birth_date=birth, calibration=False, today=TODAY)
    second = compute(chart, birth_date=birth, calibration=False, today=TODAY)
    assert first.archetype == second.archetype
    assert first.factors.notes == second.factors.notes


def test_without_birth_time_still_gives_a_type() -> None:
    result = _result(chart=_chart(has_time=False))
    assert result.factors.has_time is False
    assert result.factors.fifth_sign is None
    assert result.archetype in ARCHETYPE_TAGLINE


# ─────────────────────────── категоричный тон ───────────────────────────


def _answer(**overrides) -> product.KidsBondAnswer:
    data = {
        "archetype_line": "Ты — родитель-опора, рядом с которым ребёнку спокойно.",
        "why_in_chart": "Луна в Раке в 4 доме держит дом на тебе. " * 3,
        "strength": "Ты замечаешь усталость ребёнка раньше него самого. " * 3,
        "tension": "Ты закрываешь разговор там, где нужен вопрос. " * 3,
        "inherited": "Ты повторяешь материнскую привычку молчать о трудном. " * 3,
        "childs_view": (
            "С мамой надёжно, она всегда рядом и всё выдержит. "
            "Но я не всегда понимаю, о чём она молчит, и боюсь спросить."
        ),
        "actions": [
            "На этой неделе спроси ребёнка, что его сегодня расстроило, и промолчи минуту.",
            "Один вечер отдай ему выбор ужина целиком, без правок.",
        ],
    }
    data.update(overrides)
    return product.KidsBondAnswer(**data)


def test_childless_branch_forbids_instructions_about_a_child() -> None:
    """Человеку без детей не выдаём «поиграй с ребёнком» — его нет."""
    childless = _result(has_children=False)
    answer = _answer(
        when_it_starts="В момент, когда ребёнок появится, ты включишь режим охраны. " * 3,
        actions=[
            "Составь список из трёх вещей, которые тебе запрещали в детстве, и сделай их.",
            "Каждый вечер записывай момент, когда ты испугалась за будущее.",
        ],
    )
    assert product.validate(answer, product.ACTIONS_EXPECTED, childless) is None

    with_child = answer.model_copy(
        update={"actions": ["Проведи с ребёнком двадцать минут молча, просто рядом.", answer.actions[1]]},
    )
    assert (
        product.validate(with_child, product.ACTIONS_EXPECTED, childless)
        == "action_about_missing_child"
    )


def test_childless_branch_requires_the_switch_on_block() -> None:
    childless = _result(has_children=False)
    assert (
        product.validate(_answer(), product.ACTIONS_EXPECTED, childless)
        == "when_it_starts_missing"
    )


def test_parent_branch_keeps_actions_with_the_child() -> None:
    parent = _result(has_children=True)
    assert product.validate(_answer(), product.ACTIONS_EXPECTED, parent) is None


def test_rendered_answer_differs_by_branch() -> None:
    parent_html = product.render_answer(_answer(), _result(has_children=True))
    assert "Что делать" in parent_html
    assert "Что включится" not in parent_html

    childless = _result(has_children=False)
    answer = _answer(
        when_it_starts="В момент, когда ребёнок появится, ты включишь режим охраны. " * 3,
        actions=[
            "Составь список из трёх вещей, которые тебе запрещали в детстве, и сделай их.",
            "Каждый вечер записывай момент, когда ты испугалась за будущее.",
        ],
    )
    childless_html = product.render_answer(answer, childless)
    assert "Что включится, когда ребёнок появится" in childless_html
    assert "Что сделать до этого" in childless_html


def test_hedging_word_sends_answer_to_retry() -> None:
    """Смягчители запрещены: тон продукта утверждён категоричным."""
    assert product.validate(_answer(), product.ACTIONS_EXPECTED) is None
    hedged = _answer(strength="Возможно, ребёнку будет спокойно рядом с тобой. " * 3)
    assert (product.validate(hedged, product.ACTIONS_EXPECTED) or "").startswith("hedging")


def test_every_hedging_word_is_caught() -> None:
    for word in product.HEDGING_WORDS:
        assert product.find_hedging(f"Ты {word} делаешь это") == word


def test_prediction_about_the_child_is_rejected() -> None:
    """Категоричность про родителя — да, про судьбу ребёнка — никогда."""
    bad = _answer(tension="Судьба ребёнка сложится тяжело из-за твоего контроля. " * 3)
    assert product.validate(bad, product.ACTIONS_EXPECTED) == "child_prediction_not_allowed"


def test_two_actions_are_required() -> None:
    one = _answer(actions=["Спроси ребёнка о его дне и дослушай до конца."])
    assert product.validate(one, product.ACTIONS_EXPECTED) == "actions_count_mismatch"


def test_expected_blocks_is_the_number_of_actions() -> None:
    assert product.expected_blocks(_result()) == product.ACTIONS_EXPECTED


# ─────────────────────────── выдача ───────────────────────────


def test_rendered_answer_keeps_all_blocks() -> None:
    html = product.render_answer(_answer(), _result())
    assert "Что ребёнок получит от тебя" in html
    assert "Где будет напряжение" in html
    assert "Что ты повторяешь за своими родителями" in html
    assert "Каким тебя видит ребёнок" in html
    assert html.count("•") == product.ACTIONS_EXPECTED


def test_card_shows_the_type() -> None:
    result = _result()
    caption = product.card_caption(result)
    assert result.archetype in caption
    assert result.tagline in caption
    assert render_card(result).startswith(b"\x89PNG")


def test_product_is_registered() -> None:
    entry = get_product(QUESTION_KIDS_BOND)
    assert entry is not None
    assert entry.calibration_field == "has_children"
    assert entry.invoice_title == "Отношения с детьми"
