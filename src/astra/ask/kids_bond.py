"""«Какими будут отношения с детьми?» — тип родителя и связь с ребёнком.

Продукт отвечает про родителя, а не про ребёнка: сильные стороны, слепые зоны,
что человек неосознанно повторяет за своими родителями и каким его видит
ребёнок. Утверждений о судьбе, здоровье или талантах самого ребёнка здесь нет —
это граница продукта, и она держится схемой ответа, а не доброй волей модели.

Тип родителя считает Python по фиксированной таблице: 5 дом и его управитель,
Луна и её аспекты, Сатурн, Меркурий. LLM тип не выбирает и не заменяет.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from astra.astro.constants import SIGN_RU_TO_CLASSIC_RULER
from astra.astro.schemas import ChartPoint, FullNatalChart

METHODOLOGY_VERSION = 1

ARCHETYPE_SUPPORT = "Опора"
ARCHETYPE_FRIEND = "Друг"
ARCHETYPE_MENTOR = "Наставник"
ARCHETYPE_GUARD = "Защитник"
ARCHETYPE_MUSE = "Вдохновитель"
ARCHETYPE_KEEPER = "Хранитель дома"
ARCHETYPE_GUIDE = "Проводник"

# Короткая подпись под тип — идёт на карточку, поэтому фиксирована в коде.
ARCHETYPE_TAGLINE: dict[str, str] = {
    ARCHETYPE_SUPPORT: "растит через надёжность",
    ARCHETYPE_FRIEND: "растит через свободу",
    ARCHETYPE_MENTOR: "растит через объяснение",
    ARCHETYPE_GUARD: "растит через защиту",
    ARCHETYPE_MUSE: "растит через чувство",
    ARCHETYPE_KEEPER: "растит через дом и быт",
    ARCHETYPE_GUIDE: "растит через мир вокруг",
}

# Порядок разрешения ничьих: жёсткие фигуры перевешивают мягкие, иначе тип
# «плавал» бы между двумя равными вариантами от прогона к прогону.
_PRIORITY: tuple[str, ...] = (
    ARCHETYPE_SUPPORT,
    ARCHETYPE_GUARD,
    ARCHETYPE_MENTOR,
    ARCHETYPE_KEEPER,
    ARCHETYPE_GUIDE,
    ARCHETYPE_MUSE,
    ARCHETYPE_FRIEND,
)

_HARD_ASPECTS = frozenset({"соединение", "квадрат", "оппозиция"})

_ELEMENT_BY_SIGN: dict[str, str] = {
    "Овен": "огонь",
    "Лев": "огонь",
    "Стрелец": "огонь",
    "Телец": "земля",
    "Дева": "земля",
    "Козерог": "земля",
    "Близнецы": "воздух",
    "Весы": "воздух",
    "Водолей": "воздух",
    "Рак": "вода",
    "Скорпион": "вода",
    "Рыбы": "вода",
}

# Стиль близости по стихии Луны — база, которую потом правят её аспекты.
_MOON_MODEL_BY_ELEMENT: dict[str, str] = {
    "огонь": "яркая, эмоционально щедрая близость",
    "земля": "близость через заботу и быт",
    "воздух": "близость через разговор и объяснение",
    "вода": "глубокая, чувствующая близость",
}

_MOON_MODEL_BY_ASPECT: dict[str, str] = {
    "Saturn": "закрытая, контролирующая близость",
    "Uranus": "непредсказуемая близость, на дистанции",
    "Neptune": "жертвенная, растворяющаяся близость",
    "Pluto": "интенсивная близость с контролем",
}

_TALK_BY_ELEMENT: dict[str, str] = {
    "огонь": "прямой, эмоциональный",
    "земля": "конкретный, по делу",
    "воздух": "быстрый, объясняющий, много слов",
    "вода": "через настроение и намёк",
}


class KidsBondFactors(BaseModel):
    """Факторы связи с ребёнком. Идут в промпт и называются в ответе вслух."""

    has_time: bool
    fifth_sign: str | None = None
    planets_in_fifth: list[str] = Field(default_factory=list)
    ruler_fifth: str | None = None
    ruler_fifth_sign: str | None = None
    ruler_fifth_house: int | None = None
    moon_sign: str | None = None
    moon_house: int | None = None
    moon_aspects: list[str] = Field(default_factory=list)
    mercury_sign: str | None = None
    saturn_house: int | None = None
    moon_parenting_model: str | None = None
    mercury_talk_style: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class KidsBondResult(BaseModel):
    """Тип родителя и факторы, из которых он выведен."""

    methodology_version: int
    archetype: str
    tagline: str
    age: int
    has_children: bool
    factors: KidsBondFactors


RESULT_MODEL = KidsBondResult


def _point(chart: FullNatalChart, name: str) -> ChartPoint | None:
    return next((p for p in chart.points if p.name == name), None)


def _aspects_with(chart: FullNatalChart, point_name: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for aspect in chart.aspects:
        if aspect.p1 == point_name:
            pairs.append((aspect.p2, aspect.aspect))
        elif aspect.p2 == point_name:
            pairs.append((aspect.p1, aspect.aspect))
    return pairs


def _fifth_cusp_sign(chart: FullNatalChart) -> str | None:
    if not chart.has_time or not chart.houses:
        return None
    cusp = next((h for h in chart.houses if h.number == 5), None)
    return cusp.sign if cusp else None


def _age(birth_date: date, today: date) -> int:
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def _add(scores: dict[str, float], archetype: str, weight: float) -> None:
    scores[archetype] = scores.get(archetype, 0.0) + weight


def _collect_factors(chart: FullNatalChart) -> KidsBondFactors:
    """Факторы карты + баллы архетипов. Здесь же формулировки для промпта."""
    notes: list[str] = []
    scores: dict[str, float] = {}

    fifth_sign = _fifth_cusp_sign(chart)
    moon = _point(chart, "Moon")
    mercury = _point(chart, "Mercury")
    saturn = _point(chart, "Saturn")

    factors = KidsBondFactors(
        has_time=chart.has_time,
        fifth_sign=fifth_sign,
        moon_sign=moon.sign if moon else None,
        moon_house=moon.house if moon else None,
        mercury_sign=mercury.sign if mercury else None,
        saturn_house=saturn.house if saturn else None,
    )

    # 1. Стихия 5 дома — как человек вообще ведёт себя с детьми.
    if fifth_sign:
        element = _ELEMENT_BY_SIGN.get(fifth_sign)
        notes.append(f"5 дом в знаке {fifth_sign}")
        if element == "огонь":
            _add(scores, ARCHETYPE_GUIDE, 1.0)
            _add(scores, ARCHETYPE_FRIEND, 0.5)
        elif element == "земля":
            _add(scores, ARCHETYPE_SUPPORT, 1.0)
            _add(scores, ARCHETYPE_KEEPER, 0.5)
        elif element == "воздух":
            _add(scores, ARCHETYPE_MENTOR, 1.0)
            _add(scores, ARCHETYPE_FRIEND, 0.5)
        elif element == "вода":
            _add(scores, ARCHETYPE_MUSE, 1.0)
            _add(scores, ARCHETYPE_GUARD, 0.5)

    # 2. Планеты в 5 доме — прямое влияние на манеру.
    if chart.has_time:
        in_fifth = [p for p in chart.points if p.house == 5]
        factors.planets_in_fifth = [p.name_ru for p in in_fifth]
        if in_fifth:
            notes.append("в 5 доме: " + ", ".join(factors.planets_in_fifth))
        for point in in_fifth:
            _add(scores, _ARCHETYPE_BY_PLANET.get(point.name, ARCHETYPE_FRIEND), 1.0)

    # 3. Управитель 5 дома.
    if fifth_sign:
        ruler_name = SIGN_RU_TO_CLASSIC_RULER.get(fifth_sign)
        ruler = _point(chart, ruler_name) if ruler_name else None
        if ruler:
            factors.ruler_fifth = ruler.name_ru
            factors.ruler_fifth_sign = ruler.sign
            factors.ruler_fifth_house = ruler.house
            notes.append(
                f"управитель 5 дома — {ruler.name_ru} в {ruler.sign}"
                + (f", {ruler.house} дом" if ruler.house else ""),
            )
            _add(scores, _ARCHETYPE_BY_PLANET.get(ruler.name, ARCHETYPE_FRIEND), 1.2)

    # 4. Луна — модель близости, унаследованная от своих родителей.
    if moon:
        element = _ELEMENT_BY_SIGN.get(moon.sign)
        model = _MOON_MODEL_BY_ELEMENT.get(element or "", "близость по-своему")
        notes.append(
            f"Луна в {moon.sign}" + (f", {moon.house} дом" if moon.house else ""),
        )
        for other, aspect_ru in _aspects_with(chart, "Moon"):
            if other in _MOON_MODEL_BY_ASPECT and aspect_ru in _HARD_ASPECTS:
                other_point = _point(chart, other)
                phrase = f"Луна — {aspect_ru} — {other_point.name_ru if other_point else other}"
                factors.moon_aspects.append(phrase)
                notes.append(phrase)
                model = _MOON_MODEL_BY_ASPECT[other]
                if other == "Saturn":
                    _add(scores, ARCHETYPE_SUPPORT, 1.0)
                elif other == "Uranus":
                    _add(scores, ARCHETYPE_FRIEND, 1.0)
                elif other == "Neptune":
                    _add(scores, ARCHETYPE_MUSE, 1.0)
                elif other == "Pluto":
                    _add(scores, ARCHETYPE_GUARD, 1.0)
        factors.moon_parenting_model = model
        if moon.house == 4:
            _add(scores, ARCHETYPE_KEEPER, 1.0)

    # 5. Меркурий — как человек разговаривает с ребёнком.
    if mercury:
        element = _ELEMENT_BY_SIGN.get(mercury.sign)
        factors.mercury_talk_style = _TALK_BY_ELEMENT.get(element or "", "по-своему")
        notes.append(f"Меркурий в {mercury.sign} — {factors.mercury_talk_style} разговор")
        if element == "воздух":
            _add(scores, ARCHETYPE_MENTOR, 0.5)

    # 6. Сатурн на вершине карты — родитель-структура.
    if saturn and saturn.house in (1, 4, 10):
        notes.append(f"Сатурн в {saturn.house} доме")
        _add(scores, ARCHETYPE_SUPPORT, 0.8)

    factors.scores = {k: round(v, 2) for k, v in scores.items()}
    factors.notes = notes
    return factors


# Планета в 5 доме или управитель 5 → какой тип родителя она задаёт.
_ARCHETYPE_BY_PLANET: dict[str, str] = {
    "Sun": ARCHETYPE_GUIDE,
    "Moon": ARCHETYPE_KEEPER,
    "Mercury": ARCHETYPE_MENTOR,
    "Venus": ARCHETYPE_MUSE,
    "Mars": ARCHETYPE_GUARD,
    "Jupiter": ARCHETYPE_GUIDE,
    "Saturn": ARCHETYPE_SUPPORT,
    "Uranus": ARCHETYPE_FRIEND,
    "Neptune": ARCHETYPE_MUSE,
    "Pluto": ARCHETYPE_GUARD,
    "Chiron": ARCHETYPE_MENTOR,
}


def _pick_archetype(scores: dict[str, float]) -> str:
    """Тип с наибольшим баллом; ничья решается фиксированным приоритетом."""
    if not scores:
        return ARCHETYPE_SUPPORT
    best = max(scores.values())
    winners = [name for name, value in scores.items() if value == best]
    for name in _PRIORITY:
        if name in winners:
            return name
    return winners[0]


def compute(
    chart: FullNatalChart,
    *,
    birth_date: date,
    calibration: bool,
    today: date | None = None,
) -> KidsBondResult:
    """Тип родителя и факторы, из которых он выведен."""
    today = today or date.today()
    factors = _collect_factors(chart)
    archetype = _pick_archetype(factors.scores)
    return KidsBondResult(
        methodology_version=METHODOLOGY_VERSION,
        archetype=archetype,
        tagline=ARCHETYPE_TAGLINE[archetype],
        age=_age(birth_date, today),
        has_children=calibration,
        factors=factors,
    )


def render_card(result: KidsBondResult) -> bytes:
    """Карточка продукта: тип родителя крупно."""
    from astra.ask.card import render_card as draw

    return draw(
        hero=result.archetype,
        label="твой тип\nродителя",
        footnote=result.tagline,
    )
