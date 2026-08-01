"""«Черты моего судьбоносного партнёра?» — типаж партнёра по карте.

Продукт отвечает на «кто он», а не на «где и когда»: место встречи и сроки —
это отдельный вопрос раздела («Где меня ждёт судьбоносная встреча?»), и граница
между ними держится здесь. Из дома управителя 7 берём только среду, откуда
человек приходит, — штрих к портрету, без маршрутов и дат.

Типаж считает Python по фиксированной таблице: знак на десценденте, планеты в
7 доме, управитель 7 дома со своим знаком и домом, Венера, Марс и жёсткие
аспекты к ним. LLM типаж не выбирает и не заменяет — она его объясняет.

Род партнёра («он» / «она» / нейтрально) считается не здесь, а в промпте по
полу из профиля: карта пол партнёра не показывает.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from astra.astro.constants import (
    SIGN_RU_PREPOSITIONAL,
    SIGN_RU_TO_CLASSIC_RULER,
    SIGN_RU_TO_MODALITY,
)
from astra.astro.schemas import ChartPoint, FullNatalChart

METHODOLOGY_VERSION = 1

ARCHETYPE_ROCK = "Скала"
ARCHETYPE_FLAME = "Пламя"
ARCHETYPE_MIND = "Разум"
ARCHETYPE_DEPTH = "Глубина"
ARCHETYPE_WANDERER = "Странник"
ARCHETYPE_KEEPER = "Хранитель"
ARCHETYPE_LIGHT = "Свет"
ARCHETYPE_WIND = "Ветер"

# Подпись под типаж: идёт на карточку, поэтому зафиксирована в коде, а не у модели.
ARCHETYPE_TAGLINE: dict[str, str] = {
    ARCHETYPE_ROCK: "держит, а не обещает",
    ARCHETYPE_FLAME: "его видно в комнате",
    ARCHETYPE_MIND: "цепляет разговором",
    ARCHETYPE_DEPTH: "до дна или никак",
    ARCHETYPE_WANDERER: "приходит из другого мира",
    ARCHETYPE_KEEPER: "строит дом, а не роман",
    ARCHETYPE_LIGHT: "делает жизнь красивее",
    ARCHETYPE_WIND: "появляется внезапно",
}

# Порядок разрешения ничьих: структурные фигуры перевешивают лёгкие. Без него
# типаж «плавал» бы между двумя равными вариантами, а карта одна — ответ один.
_PRIORITY: tuple[str, ...] = (
    ARCHETYPE_ROCK,
    ARCHETYPE_DEPTH,
    ARCHETYPE_WANDERER,
    ARCHETYPE_KEEPER,
    ARCHETYPE_MIND,
    ARCHETYPE_FLAME,
    ARCHETYPE_LIGHT,
    ARCHETYPE_WIND,
)

_HARD_ASPECTS = frozenset({"соединение", "квадрат", "оппозиция"})

# Знак → (основной типаж, оттенок). Оттенок вполсилы: он разводит ничьи и
# добавляет портрету вторую краску, не перебивая основную.
_ARCHETYPE_BY_SIGN: dict[str, tuple[str, str]] = {
    "Овен": (ARCHETYPE_FLAME, ARCHETYPE_WIND),
    # Телец — про уют и достаток, а не про строгость: основное у него «Хранитель».
    "Телец": (ARCHETYPE_KEEPER, ARCHETYPE_ROCK),
    "Близнецы": (ARCHETYPE_MIND, ARCHETYPE_WIND),
    "Рак": (ARCHETYPE_KEEPER, ARCHETYPE_DEPTH),
    "Лев": (ARCHETYPE_FLAME, ARCHETYPE_LIGHT),
    # Дева — Меркурий: сначала ум и разбор, следом забота о быте.
    "Дева": (ARCHETYPE_MIND, ARCHETYPE_KEEPER),
    "Весы": (ARCHETYPE_LIGHT, ARCHETYPE_MIND),
    "Скорпион": (ARCHETYPE_DEPTH, ARCHETYPE_ROCK),
    "Стрелец": (ARCHETYPE_WANDERER, ARCHETYPE_FLAME),
    "Козерог": (ARCHETYPE_ROCK, ARCHETYPE_DEPTH),
    # Водолей — про инаковость: «Странник» ему ближе, чем «Разум».
    "Водолей": (ARCHETYPE_WIND, ARCHETYPE_WANDERER),
    # Классический управитель Рыб — Юпитер: человек «не отсюда», а мягкость вторым слоем.
    "Рыбы": (ARCHETYPE_WANDERER, ARCHETYPE_LIGHT),
}

_SHADE_FACTOR = 0.4

# Планета в 7 доме или управитель 7 дома → какой типаж она задаёт.
_ARCHETYPE_BY_PLANET: dict[str, str] = {
    "Sun": ARCHETYPE_FLAME,
    "Moon": ARCHETYPE_KEEPER,
    "Mercury": ARCHETYPE_MIND,
    "Venus": ARCHETYPE_LIGHT,
    "Mars": ARCHETYPE_FLAME,
    "Jupiter": ARCHETYPE_WANDERER,
    "Saturn": ARCHETYPE_ROCK,
    "Uranus": ARCHETYPE_WIND,
    "Neptune": ARCHETYPE_LIGHT,
    "Pluto": ARCHETYPE_DEPTH,
    "Chiron": ARCHETYPE_MIND,
}

# Дом управителя 7 → типаж. Дом отвечает на «из какой он среды», а среда
# заметно красит характер: 9 дом даёт другого человека, чем 4.
_ARCHETYPE_BY_HOUSE: dict[int, str] = {
    1: ARCHETYPE_FLAME,
    2: ARCHETYPE_ROCK,
    3: ARCHETYPE_MIND,
    4: ARCHETYPE_KEEPER,
    5: ARCHETYPE_FLAME,
    6: ARCHETYPE_KEEPER,
    7: ARCHETYPE_LIGHT,
    8: ARCHETYPE_DEPTH,
    9: ARCHETYPE_WANDERER,
    10: ARCHETYPE_ROCK,
    11: ARCHETYPE_WIND,
    12: ARCHETYPE_DEPTH,
}

# Тот же дом словами: среда, откуда человек приходит. Только среда — без мест
# и сроков, они принадлежат вопросу «Где меня ждёт судьбоносная встреча?».
_ORIGIN_BY_HOUSE: dict[int, str] = {
    1: "из твоего же круга, совсем рядом",
    2: "через общие дела и деньги",
    3: "через учёбу, поездки и общих знакомых",
    4: "из семейного круга или земляк",
    5: "там, где отдыхают и творят",
    6: "через работу и каждодневные дела",
    7: "через людей, которые вас познакомят",
    8: "через общее дело, где на кону многое",
    9: "из другой страны или другой среды",
    10: "через работу и статус",
    11: "через друзей и сообщества",
    12: "из закрытой среды, не на виду",
}

# Жёсткий аспект к управителю 7 или к Венере правит типаж поверх знака.
_ARCHETYPE_BY_ASPECT: dict[str, str] = {
    "Saturn": ARCHETYPE_ROCK,
    "Uranus": ARCHETYPE_WIND,
    "Neptune": ARCHETYPE_LIGHT,
    "Pluto": ARCHETYPE_DEPTH,
}

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

# Как он говорит — по стихии знака управителя 7 (без времени — Венеры).
_PACE_BY_ELEMENT: dict[str, str] = {
    "огонь": "говорит быстро и прямо, без подходов",
    "земля": "говорит медленно и весомо, лишнего не скажет",
    "воздух": "говорит много и легко, перескакивает с темы на тему",
    "вода": "говорит тихо, с паузами, больше слушает",
}

# Как он держится — по модальности знака на десценденте (без времени — Венеры).
_BEARING_BY_MODALITY: dict[str, str] = {
    "кардинальный": "первым идёт на контакт и первым принимает решения",
    "фиксированный": "не суетится, стоит на своём и ждёт, пока подойдут",
    "мутабельный": "легко подстраивается и так же легко меняет планы",
}

# Формулировки нейтральны по роду: партнёр может быть любого пола, а строки
# эти пишет код и подставляет в ответ как есть, без участия модели.
AGE_OLDER = "скорее старше тебя"
AGE_PEER = "примерно твоих лет"
AGE_YOUNGER = "скорее младше тебя"

# Откат для возраста, когда ни Сатурн, ни Уран партнёрских точек не касаются.
_OLDER_SIGNS = frozenset({"Козерог", "Телец", "Дева", "Скорпион"})
_YOUNGER_SIGNS = frozenset({"Овен", "Близнецы", "Лев", "Водолей"})

# Веса факторов. Утверждены до кода, правятся по распределению на выборке карт.
_W_DSC_SIGN = 1.0
_W_PLANET_IN_SEVENTH = 1.2
_W_RULER_SIGN = 1.0
_W_RULER_HOUSE = 0.8
_W_VENUS_SIGN = 0.6
_W_HARD_ASPECT = 0.8
_W_MARS_SIGN = 0.4

# Без времени рождения десцендента и домов нет: Венера остаётся единственной
# опорой, поэтому её вес поднимаем до веса десцендента. Дома не трогаем вовсе.
_NO_TIME_VENUS_WEIGHT = 1.0

# Точки, которые считаем «партнёрскими» в 7 доме. Узлы и Лилит не берём:
# они говорят о задаче человека, а не о характере того, кто придёт.
_PARTNER_POINTS = frozenset(_ARCHETYPE_BY_PLANET)


class PartnerTraitsFactors(BaseModel):
    """Факторы карты, из которых выведен типаж. Модель называет их вслух."""

    has_time: bool
    dsc_sign: str | None = None
    dsc_modality: str | None = None
    planets_in_seventh: list[str] = Field(default_factory=list)
    ruler_seventh: str | None = None
    ruler_seventh_sign: str | None = None
    ruler_seventh_house: int | None = None
    venus_sign: str | None = None
    venus_aspects: list[str] = Field(default_factory=list)
    ruler_aspects: list[str] = Field(default_factory=list)
    mars_sign: str | None = None
    saturn_in_seventh: bool = False
    scores: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class PartnerTraitsResult(BaseModel):
    """Типаж партнёра и штрихи к портрету, посчитанные детерминированно."""

    methodology_version: int
    archetype: str
    shade: str | None = None  # вторая краска портрета, если она отличается
    tagline: str
    age_hint: str
    origin: str | None = None  # среда, откуда он; без времени рождения — None
    pace: str | None = None
    bearing: str | None = None
    age: int
    in_relationship: bool
    factors: PartnerTraitsFactors


RESULT_MODEL = PartnerTraitsResult


def _point(chart: FullNatalChart, name: str) -> ChartPoint | None:
    return next((p for p in chart.points if p.name == name), None)


def _aspects_with(chart: FullNatalChart, point_name: str) -> list[tuple[str, str]]:
    """Аспекты точки: [(вторая точка en, аспект по-русски)]."""
    pairs: list[tuple[str, str]] = []
    for aspect in chart.aspects:
        if aspect.p1 == point_name:
            pairs.append((aspect.p2, aspect.aspect))
        elif aspect.p2 == point_name:
            pairs.append((aspect.p1, aspect.aspect))
    return pairs


def _seventh_cusp_sign(chart: FullNatalChart) -> str | None:
    if not chart.has_time or not chart.houses:
        return None
    cusp = next((h for h in chart.houses if h.number == 7), None)
    return cusp.sign if cusp else None


def _age(birth_date: date, today: date) -> int:
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def _in_sign(sign: str) -> str:
    """«в Козероге», а не «в Козерог»: формулировки уходят в ответ как есть."""
    return f"в {SIGN_RU_PREPOSITIONAL.get(sign, sign)}"


def _add(scores: dict[str, float], archetype: str, weight: float) -> None:
    scores[archetype] = scores.get(archetype, 0.0) + weight


def _score_sign(scores: dict[str, float], sign: str | None, weight: float) -> None:
    """Знак даёт основной типаж полным весом и оттенок — вполсилы."""
    pair = _ARCHETYPE_BY_SIGN.get(sign or "")
    if pair is None:
        return
    main, shade = pair
    _add(scores, main, weight)
    _add(scores, shade, weight * _SHADE_FACTOR)


def _collect_factors(chart: FullNatalChart) -> PartnerTraitsFactors:
    """Факторы карты + баллы типажей. Здесь же формулировки для промпта."""
    notes: list[str] = []
    scores: dict[str, float] = {}

    dsc_sign = _seventh_cusp_sign(chart)
    venus = _point(chart, "Venus")
    mars = _point(chart, "Mars")

    factors = PartnerTraitsFactors(
        has_time=chart.has_time,
        dsc_sign=dsc_sign,
        dsc_modality=SIGN_RU_TO_MODALITY.get(dsc_sign) if dsc_sign else None,
        venus_sign=venus.sign if venus else None,
        mars_sign=mars.sign if mars else None,
    )

    # 1. Знак на десценденте — базовый типаж того, кто приходит.
    if dsc_sign:
        _score_sign(scores, dsc_sign, _W_DSC_SIGN)
        notes.append(f"десцендент {_in_sign(dsc_sign)} ({factors.dsc_modality} знак)")

    # 2. Планеты в 7 доме — самый громкий маркер, перебивает знак.
    if chart.has_time:
        in_seventh = [p for p in chart.points if p.house == 7 and p.name in _PARTNER_POINTS]
        factors.planets_in_seventh = [p.name_ru for p in in_seventh]
        factors.saturn_in_seventh = any(p.name == "Saturn" for p in in_seventh)
        if in_seventh:
            notes.append("в 7 доме: " + ", ".join(factors.planets_in_seventh))
        for point in in_seventh:
            _add(scores, _ARCHETYPE_BY_PLANET[point.name], _W_PLANET_IN_SEVENTH)

    # 3. Управитель 7 дома: его знак — характер, его дом — среда.
    ruler = _ruler_point(chart, dsc_sign)
    if ruler is not None:
        factors.ruler_seventh = ruler.name_ru
        factors.ruler_seventh_sign = ruler.sign
        factors.ruler_seventh_house = ruler.house
        notes.append(
            f"управитель 7 дома — {ruler.name_ru} {_in_sign(ruler.sign)}"
            + (f", {ruler.house} дом" if ruler.house else ""),
        )
        _score_sign(scores, ruler.sign, _W_RULER_SIGN)
        if ruler.house and ruler.house in _ARCHETYPE_BY_HOUSE:
            _add(scores, _ARCHETYPE_BY_HOUSE[ruler.house], _W_RULER_HOUSE)
        _score_hard_aspects(
            chart,
            scores,
            point_name=ruler.name,
            point_ru=ruler.name_ru,
            bucket=factors.ruler_aspects,
            notes=notes,
        )

    # 4. Венера — что человека притягивает. Без времени она единственная опора.
    if venus:
        weight = _W_VENUS_SIGN if chart.has_time else _NO_TIME_VENUS_WEIGHT
        _score_sign(scores, venus.sign, weight)
        notes.append(f"Венера {_in_sign(venus.sign)}")
        _score_hard_aspects(
            chart,
            scores,
            point_name="Venus",
            point_ru="Венера",
            bucket=factors.venus_aspects,
            notes=notes,
        )

    # 5. Марс — темперамент партнёра, самый лёгкий вес.
    if mars:
        _score_sign(scores, mars.sign, _W_MARS_SIGN)
        notes.append(f"Марс {_in_sign(mars.sign)}")

    factors.scores = {name: round(value, 2) for name, value in scores.items()}
    factors.notes = notes
    return factors


def _ruler_point(chart: FullNatalChart, dsc_sign: str | None) -> ChartPoint | None:
    if not dsc_sign:
        return None
    ruler_name = SIGN_RU_TO_CLASSIC_RULER.get(dsc_sign)
    return _point(chart, ruler_name) if ruler_name else None


def _score_hard_aspects(
    chart: FullNatalChart,
    scores: dict[str, float],
    *,
    point_name: str,
    point_ru: str,
    bucket: list[str],
    notes: list[str],
) -> None:
    """Жёсткие аспекты с Сатурном, Ураном, Нептуном и Плутоном."""
    seen: set[str] = set()
    for other, aspect_ru in _aspects_with(chart, point_name):
        archetype = _ARCHETYPE_BY_ASPECT.get(other)
        if archetype is None or aspect_ru not in _HARD_ASPECTS or other in seen:
            continue
        seen.add(other)
        _add(scores, archetype, _W_HARD_ASPECT)
        other_point = _point(chart, other)
        phrase = f"{point_ru} — {aspect_ru} — {other_point.name_ru if other_point else other}"
        bucket.append(phrase)
        notes.append(phrase)


def _pick_archetype(scores: dict[str, float]) -> str:
    """Типаж с наибольшим баллом; ничья решается фиксированным приоритетом."""
    if not scores:
        return ARCHETYPE_ROCK
    best = max(scores.values())
    winners = [name for name, value in scores.items() if value == best]
    for name in _PRIORITY:
        if name in winners:
            return name
    return winners[0]


def _pick_shade(scores: dict[str, float], archetype: str) -> str | None:
    """Вторая краска портрета: следующий по баллам, если он заметен."""
    rest = {name: value for name, value in scores.items() if name != archetype}
    if not rest:
        return None
    best = max(rest.values())
    if best < scores[archetype] / 2:
        return None  # слишком слаб, чтобы называть его вслух
    winners = [name for name, value in rest.items() if value == best]
    for name in _PRIORITY:
        if name in winners:
            return name
    return winners[0]


def _age_hint(chart: FullNatalChart, factors: PartnerTraitsFactors) -> str:
    """Старше или младше — по Сатурну и Урану/Юпитеру у партнёрских точек.

    Если ни один из них карту не задевает, решает знак: без этого отката две
    трети людей получали бы одно и то же безликое «ровесник».
    """
    older = factors.saturn_in_seventh or any(
        "Сатурн" in phrase for phrase in (*factors.ruler_aspects, *factors.venus_aspects)
    )
    younger = any(
        "Уран" in phrase for phrase in (*factors.ruler_aspects, *factors.venus_aspects)
    ) or any(p.name in ("Uranus", "Jupiter") for p in chart.points if p.house == 7)
    if older and not younger:
        return AGE_OLDER
    if younger and not older:
        return AGE_YOUNGER
    if older and younger:
        return AGE_PEER
    sign = factors.dsc_sign or factors.venus_sign
    if sign in _OLDER_SIGNS:
        return AGE_OLDER
    if sign in _YOUNGER_SIGNS:
        return AGE_YOUNGER
    return AGE_PEER


def compute(
    chart: FullNatalChart,
    *,
    birth_date: date,
    calibration: bool,
    today: date | None = None,
) -> PartnerTraitsResult:
    """Типаж партнёра и штрихи к портрету."""
    today = today or date.today()
    factors = _collect_factors(chart)
    archetype = _pick_archetype(factors.scores)

    ruler = _ruler_point(chart, factors.dsc_sign)
    pace_sign = ruler.sign if ruler else factors.venus_sign
    bearing_modality = factors.dsc_modality
    if bearing_modality is None:
        venus = _point(chart, "Venus")
        bearing_modality = venus.modality if venus else None

    return PartnerTraitsResult(
        methodology_version=METHODOLOGY_VERSION,
        archetype=archetype,
        shade=_pick_shade(factors.scores, archetype),
        tagline=ARCHETYPE_TAGLINE[archetype],
        age_hint=_age_hint(chart, factors),
        # Среда — только при известном времени: без домов её честно не назвать.
        origin=_ORIGIN_BY_HOUSE.get(factors.ruler_seventh_house or 0),
        pace=_PACE_BY_ELEMENT.get(_ELEMENT_BY_SIGN.get(pace_sign or "", "")),
        bearing=_BEARING_BY_MODALITY.get(bearing_modality or ""),
        age=_age(birth_date, today),
        in_relationship=calibration,
        factors=factors,
    )


def render_card(result: PartnerTraitsResult) -> bytes:
    """Карточка продукта: типаж партнёра крупно."""
    from astra.ask.card import render_card as draw

    return draw(
        hero=result.archetype,
        label="твой типаж\nпартнёра",
        footnote=result.tagline,
    )
