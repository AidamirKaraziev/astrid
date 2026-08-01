"""Продукт «Черты моего судьбоносного партнёра?»: типаж, штрихи, обращение по имени."""

from datetime import date

import pytest

from astra.ask.naming import address, addressable_name
from astra.ask.partner_traits import (
    AGE_OLDER,
    AGE_YOUNGER,
    ARCHETYPE_DEPTH,
    ARCHETYPE_KEEPER,
    ARCHETYPE_ROCK,
    ARCHETYPE_TAGLINE,
    ARCHETYPE_WANDERER,
    ARCHETYPE_WIND,
    _pick_archetype,
    compute,
    render_card,
)
from astra.ask.products import QUESTION_PARTNER_TRAITS, get_product
from astra.astro.calculator import kerykeion_available
from astra.astro.schemas import ChartPoint, FullNatalChart, HouseCusp, NatalAspect
from astra.llm.prompts.ask import partner_traits as product
from astra.users.gender import GENDER_FEMALE, GENDER_MALE

TODAY = date(2026, 8, 1)
BORN = date(1990, 3, 15)

pytestmark = pytest.mark.skipif(not kerykeion_available(), reason="kerykeion не установлен")


def _chart(
    *,
    dsc_sign: str = "Козерог",
    ruler_planet: str = "Saturn",
    ruler_sign: str = "Козерог",
    ruler_house: int = 10,
    venus_sign: str = "Телец",
    mars_sign: str = "Овен",
    planets_in_seventh: tuple[tuple[str, str], ...] = (),
    aspects: list[NatalAspect] | None = None,
    has_time: bool = True,
) -> FullNatalChart:
    """Синтетическая карта: проверяем правила, а не эфемериды.

    `ruler_planet` — та точка, что окажется управителем 7 дома при выбранном
    знаке на десценденте: для Козерога это Сатурн, для Рыб — Юпитер.
    """
    points = [
        ChartPoint(
            name="Venus", name_ru="Венера", lon=45.0, sign=venus_sign,
            sign_deg=15.0, house=5, modality="фиксированный",
        ),
        ChartPoint(
            name="Mars", name_ru="Марс", lon=10.0, sign=mars_sign, sign_deg=10.0, house=1,
        ),
        ChartPoint(name="Saturn", name_ru="Сатурн", lon=300.0, sign="Козерог", sign_deg=5.0, house=10),
        ChartPoint(name="Uranus", name_ru="Уран", lon=250.0, sign="Стрелец", sign_deg=10.0, house=9),
        ChartPoint(name="Neptune", name_ru="Нептун", lon=280.0, sign="Козерог", sign_deg=8.0, house=10),
        ChartPoint(name="Pluto", name_ru="Плутон", lon=230.0, sign="Скорпион", sign_deg=15.0, house=8),
        ChartPoint(name="Jupiter", name_ru="Юпитер", lon=100.0, sign="Рак", sign_deg=10.0, house=4),
        ChartPoint(name="Moon", name_ru="Луна", lon=120.0, sign="Рак", sign_deg=12.0, house=4),
        ChartPoint(name="Mercury", name_ru="Меркурий", lon=70.0, sign="Близнецы", sign_deg=5.0, house=3),
        ChartPoint(name="Sun", name_ru="Солнце", lon=355.0, sign="Рыбы", sign_deg=25.0, house=12),
    ]
    for point in points:
        if point.name == ruler_planet:
            point.sign, point.house = ruler_sign, ruler_house
            break
    for name, name_ru in planets_in_seventh:
        for point in points:
            if point.name == name:
                point.house = 7
                break
        else:  # pragma: no cover — страховка от опечатки в тесте
            raise AssertionError(f"точки {name_ru} нет в тестовой карте")
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


def _result(chart: FullNatalChart | None = None, *, in_relationship: bool = False):
    return compute(
        chart if chart is not None else _chart(),
        birth_date=BORN,
        calibration=in_relationship,
        today=TODAY,
    )


# ─────────────────────────────── типаж ───────────────────────────────


def test_earth_descendant_gives_rock() -> None:
    """Козерог на десценденте и управитель там же — «Скала»."""
    assert _result().archetype == ARCHETYPE_ROCK


def test_planet_in_seventh_outweighs_the_sign() -> None:
    """Уран в 7 доме перебивает знак: самый громкий маркер партнёрства."""
    chart = _chart(
        dsc_sign="Водолей",
        ruler_sign="Водолей",
        ruler_house=11,
        planets_in_seventh=(("Uranus", "Уран"),),
    )
    assert _result(chart).archetype == ARCHETYPE_WIND


def test_pisces_descendant_gives_wanderer() -> None:
    """Рыбы ведут к «Страннику»: их классический управитель — Юпитер."""
    chart = _chart(
        dsc_sign="Рыбы",
        ruler_planet="Jupiter",
        ruler_sign="Стрелец",
        ruler_house=9,
        venus_sign="Рыбы",
    )
    assert _result(chart).archetype == ARCHETYPE_WANDERER


def test_tie_is_resolved_by_fixed_priority() -> None:
    """Ничья решается приоритетом, иначе типаж «плавал» бы от прогона к прогону."""
    assert _pick_archetype({ARCHETYPE_WIND: 2.0, ARCHETYPE_ROCK: 2.0}) == ARCHETYPE_ROCK
    assert _pick_archetype({}) == ARCHETYPE_ROCK


def test_same_chart_gives_same_type() -> None:
    """Карта одна — типаж один: иначе на повторной покупке доверие кончится."""
    chart = _chart()
    assert _result(chart).archetype == _result(chart).archetype


def test_every_archetype_has_a_tagline() -> None:
    for archetype in ARCHETYPE_TAGLINE:
        assert ARCHETYPE_TAGLINE[archetype]


# ───────────────────────── штрихи к портрету ─────────────────────────


def test_saturn_in_seventh_makes_the_partner_older() -> None:
    chart = _chart(planets_in_seventh=(("Saturn", "Сатурн"),))
    assert _result(chart).age_hint == AGE_OLDER


def test_uranus_aspect_to_venus_makes_the_partner_younger() -> None:
    chart = _chart(
        dsc_sign="Близнецы",
        ruler_sign="Близнецы",
        ruler_house=3,
        aspects=[_aspect("Venus", "Венера", "Uranus", "Уран")],
    )
    assert _result(chart).age_hint == AGE_YOUNGER


def test_origin_comes_from_the_rulers_house() -> None:
    chart = _chart(ruler_house=9)
    assert "другой страны" in (_result(chart).origin or "")


def test_no_birth_time_drops_houses_but_keeps_the_type() -> None:
    """Без времени рождения дома не выдумываем, но продукт всё равно отвечает."""
    result = _result(_chart(has_time=False))
    assert result.origin is None
    assert result.factors.dsc_sign is None
    assert result.archetype in ARCHETYPE_TAGLINE
    assert result.bearing  # манеру держаться берём по Венере


def test_shade_is_dropped_when_it_is_too_weak() -> None:
    assert _pick_archetype({ARCHETYPE_ROCK: 4.0}) == ARCHETYPE_ROCK
    result = _result()
    if result.shade is not None:
        assert result.factors.scores[result.shade] >= result.factors.scores[result.archetype] / 2


# ────────────────────────── обращение по имени ──────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Аня", "Аня"),
        ("аня", "Аня"),
        ("АНЯ", "Аня"),
        ("Аня 🌸", "Аня"),
        ("Анна-Мария", "Анна-Мария"),
        ("Ajdamir", None),  # латиница — не зовём
        ("user123", None),
        ("друг", None),  # подстановка бота
        ("", None),
        (None, None),
        ("Я", None),  # слишком коротко
    ],
)
def test_addressable_name(raw, expected) -> None:
    assert addressable_name(raw) == expected


def test_address_lowercases_the_continuation() -> None:
    assert address("Твоя карта показывает", "Аня") == "Аня, твоя карта показывает"


def test_address_keeps_planets_capitalised() -> None:
    """«Аня, венера…» — недопустимо: имена планет остаются с заглавной."""
    assert address("Венера в твоей карте", "Аня") == "Аня, Венера в твоей карте"


def test_address_without_a_name_reads_as_a_normal_sentence() -> None:
    assert address("твоя карта показывает", None) == "Твоя карта показывает"


def test_name_never_reaches_the_model() -> None:
    """Имя подставляет код: в сообщении для модели его быть не должно."""
    message = product.build_user_message(_result(), user_name="Аня", gender=GENDER_FEMALE)
    assert "Аня" not in message


# ──────────────────────────── род партнёра ────────────────────────────


def test_reader_gender_reaches_the_model() -> None:
    """Своим родом человека PERSONA согласует весь текст — поле обязано доехать."""
    message = product.build_user_message(_result(), gender=GENDER_MALE)
    assert '"gender": "мужчина"' in message


def test_render_capitalises_the_blocks_model_wrote_lowercase() -> None:
    """Правило «со строчной» касается только захода — остальное чинит код."""
    html_text = product.render_answer(
        _answer(portrait="он входит без шума. " + "П" * 200),
        _result(),
        user_name="Аня",
    )
    assert "Он входит без шума" in html_text


def test_partner_gender_is_opposite_by_default() -> None:
    assert product._partner_gender(GENDER_FEMALE) == "мужской"
    assert product._partner_gender(GENDER_MALE) == "женский"


def test_partner_gender_is_neutral_when_unknown() -> None:
    """Пол не задан — ничего не додумываем и не спрашиваем."""
    assert product._partner_gender(None) == "нейтральный"
    assert "нейтральный" in product.build_user_message(_result(), gender=None)


# ───────────────────────────── схема ответа ─────────────────────────────


def _answer(**overrides) -> product.PartnerTraitsAnswer:
    payload = {
        "opening": "твоя карта на удивление конкретна в этом вопросе.",
        "portrait": "П" * 200,
        "traits": [
            {"title": f"Черта {i}", "text": "Т" * 100} for i in range(1, 4)
        ],
        "recognise": ["не перебивает", "первым платит по счёту", "приходит раньше времени"],
        "glue": "Г" * 120,
        "friction": "Ф" * 120,
        "closing": "сверься с тем, кто рядом.",
    }
    payload.update(overrides)
    return product.PartnerTraitsAnswer.model_validate(payload)


def test_valid_answer_passes() -> None:
    assert product.validate(_answer(), product.expected_blocks(_result())) is None


def test_wrong_number_of_traits_is_rejected() -> None:
    answer = _answer(traits=[{"title": "Одна", "text": "Т" * 100}])
    assert product.validate(answer, 3) == "traits_count_mismatch"


def test_too_few_markers_is_rejected() -> None:
    answer = _answer(recognise=["раз", "два"])
    assert product.validate(answer, 3) == "recognise_count"


def test_banned_phrase_is_rejected() -> None:
    answer = _answer(portrait="Его энергетика считывается сразу. " + "П" * 200)
    assert (product.validate(answer, 3) or "").startswith("banned_phrase")


def test_render_puts_the_name_in_twice() -> None:
    html_text = product.render_answer(_answer(), _result(), user_name="Аня")
    assert html_text.count("Аня,") == 2


def test_render_without_a_name_has_no_dangling_comma() -> None:
    html_text = product.render_answer(_answer(), _result(), user_name=None)
    assert "," not in html_text.split("\n")[0][:1]
    assert html_text.startswith("Твоя карта")


def test_computed_markers_come_from_python_not_from_the_model() -> None:
    """Возраст, среда, речь и манера — посчитаны кодом и всегда в ответе."""
    result = _result()
    html_text = product.render_answer(_answer(), result, user_name="Аня")
    assert result.age_hint in html_text
    assert (result.origin or "") in html_text
    assert (result.pace or "") in html_text


def test_answer_never_promises_a_place_of_meeting() -> None:
    """Граница с вопросом «Где меня ждёт встреча?» держится промптом."""
    assert "BOUNDARY" in product.SYSTEM_PROMPT
    assert "a date of meeting" in product.SYSTEM_PROMPT


# ───────────────────────────── продукт целиком ─────────────────────────────


def test_product_is_wired_into_the_registry() -> None:
    loaded = get_product(QUESTION_PARTNER_TRAITS)
    assert loaded is not None
    assert loaded.methodology_version == 1
    assert loaded.render_card is not None
    assert loaded.spec.address_by_name is True


def test_teaser_greets_by_name_and_survives_without_one() -> None:
    loaded = get_product(QUESTION_PARTNER_TRAITS)
    assert loaded is not None
    assert loaded.teaser_for("Аня").startswith("Аня, смотрю")
    assert loaded.teaser_for(None).startswith("Смотрю")


def test_card_renders() -> None:
    image = render_card(_result())
    assert image[:4] == b"\x89PNG"


def test_card_caption_names_the_type() -> None:
    result = _result()
    assert result.archetype in product.card_caption(result)
