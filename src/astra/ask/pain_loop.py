"""«Почему я снова и снова обжигаюсь?» — повторяющийся сценарий в отношениях.

Продукт про **паттерн**: что человек повторяет, в какой точке отношений это
ломается и что этот круг размыкает. Откуда модель любви взялась — не сюда:
корень принадлежит вопросу «Как я сама рушу близость?», и граница держится
схемой ответа, а не доброй волей модели.

Петлю считает Python по фиксированной таблице: жёсткие аспекты Венеры и Луны
с Сатурном, Нептуном, Плутоном, Ураном и Хироном, положение Венеры и
управителя 7 дома по домам, знак на десценденте и Марс. LLM петлю не выбирает.

Транзитных окон здесь нет намеренно: петля — не событие во времени.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from astra.astro.constants import (
    SIGN_RU_PREPOSITIONAL,
    SIGN_RU_TO_CLASSIC_RULER,
)
from astra.astro.schemas import ChartPoint, FullNatalChart

METHODOLOGY_VERSION = 1

LOOP_RESCUE = "Спасение"
LOOP_DISTANCE = "Дистанция"
LOOP_ALL_IN = "До дна"
LOOP_ESCAPE = "Побег"
LOOP_MERGE = "Слияние"
LOOP_PATIENCE = "Терпение"
LOOP_FIGHT = "Борьба"

# Подпись под петлю — от первого лица: человек должен узнать себя в строке.
# Идёт на карточку, поэтому зафиксирована в коде, а не отдана модели.
LOOP_TAGLINE: dict[str, str] = {
    LOOP_RESCUE: "влюбляюсь в того, кого надо чинить",
    LOOP_DISTANCE: "выбираю тех, кто не может быть рядом",
    LOOP_ALL_IN: "либо всё, либо никак",
    LOOP_ESCAPE: "ухожу раньше, чем оставят меня",
    LOOP_MERGE: "исчезаю в другом целиком",
    LOOP_PATIENCE: "люблю в долг и жду, что оценят",
    LOOP_FIGHT: "чувствую только там, где напряжение",
}

# Что размыкает круг. Одно действие на петлю, без «полюби себя».
LOOP_WAY_OUT: dict[str, str] = {
    LOOP_RESCUE: (
        "спрашивать себя не «смогу ли я ему помочь», а «хорошо ли мне рядом» — "
        "и проверять ответ через неделю, а не через год"
    ),
    LOOP_DISTANCE: (
        "поймать момент, когда недоступность читается как глубина, — "
        "и не принимать одно за другое"
    ),
    LOOP_ALL_IN: (
        "дать отношениям побыть спокойными: ровное — не значит мёртвое, "
        "и накал не единственное доказательство любви"
    ),
    LOOP_ESCAPE: (
        "в момент, когда хочется уйти первым, сказать это вслух — "
        "именно сказать, а не исчезнуть"
    ),
    LOOP_MERGE: (
        "оставить себе то, что не отдаётся никому: одно дело, один человек, "
        "один вечер в неделю — и не сдвигать их ради близости"
    ),
    LOOP_PATIENCE: (
        "просить прямо и сразу, а не копить счёт, который потом предъявишь "
        "целиком и в самый неподходящий момент"
    ),
    LOOP_FIGHT: (
        "проверять, остаётся ли между вами что-то, когда конфликт стих: "
        "если в тишине пусто — дело не в партнёре"
    ),
}

# Порядок разрешения ничьих: тяжёлые сценарии перевешивают лёгкие, иначе петля
# «плавала» бы между двумя равными вариантами, а карта одна — ответ один.
_PRIORITY: tuple[str, ...] = (
    LOOP_ALL_IN,
    LOOP_DISTANCE,
    LOOP_RESCUE,
    LOOP_MERGE,
    LOOP_PATIENCE,
    LOOP_FIGHT,
    LOOP_ESCAPE,
)

_HARD_ASPECTS = frozenset({"соединение", "квадрат", "оппозиция"})

# Планета, задающая петлю → в какой точке отношений всё разваливается.
BREAK_POINT_BY_PLANET: dict[str, str] = {
    "Saturn": "на самом входе — подпустить близко не получается вовсе",
    "Uranus": "на сближении — ровно тогда, когда становится по-настоящему близко",
    "Neptune": "на прозрении — когда образ рассыпается и виден живой человек",
    "Pluto": "в кризисе — когда начинается борьба за то, чей верх",
    "Chiron": "в уязвимости — когда приходится показать слабое место",
}
_BREAK_POINT_DEFAULT = "на середине — когда первая лёгкость уже прошла, а доверия ещё нет"

# Жёсткий аспект Венеры (что человек выбирает) → петля и её оттенок.
_VENUS_ASPECT_LOOPS: dict[str, tuple[str, str | None]] = {
    "Saturn": (LOOP_DISTANCE, LOOP_PATIENCE),
    "Neptune": (LOOP_RESCUE, LOOP_MERGE),
    "Pluto": (LOOP_ALL_IN, LOOP_FIGHT),
    "Uranus": (LOOP_ESCAPE, None),
    "Chiron": (LOOP_RESCUE, LOOP_PATIENCE),
}

# Жёсткий аспект Луны (как человек привык чувствовать себя любимым).
_MOON_ASPECT_LOOPS: dict[str, tuple[str, str | None]] = {
    "Saturn": (LOOP_PATIENCE, LOOP_DISTANCE),
    "Neptune": (LOOP_MERGE, LOOP_RESCUE),
    "Pluto": (LOOP_ALL_IN, None),
    "Uranus": (LOOP_ESCAPE, None),
    # Луна с Хироном — это про «спасу и тогда меня полюбят», а не про терпение.
    "Chiron": (LOOP_RESCUE, LOOP_PATIENCE),
}

# Марс — злость, которой некуда деться. Партнёр становится соперником.
_MARS_ASPECT_PLANETS = frozenset({"Pluto", "Saturn", "Uranus"})

# Дом Венеры и дом управителя 7: где тема любви проживается.
_HOUSE_LOOPS: dict[int, str] = {
    6: LOOP_PATIENCE,
    8: LOOP_ALL_IN,
    12: LOOP_DISTANCE,
}

_DSC_SIGN_LOOPS: dict[str, str] = {
    "Овен": LOOP_FIGHT,
    # Телец на десценденте — не терпение, а «держу и не отпускаю».
    "Телец": LOOP_MERGE,
    "Близнецы": LOOP_ESCAPE,
    "Рак": LOOP_RESCUE,
    "Лев": LOOP_FIGHT,
    "Дева": LOOP_PATIENCE,
    "Весы": LOOP_MERGE,
    "Скорпион": LOOP_ALL_IN,
    "Стрелец": LOOP_ESCAPE,
    "Козерог": LOOP_DISTANCE,
    "Водолей": LOOP_ESCAPE,
    "Рыбы": LOOP_MERGE,
}

_SHADE_FACTOR = 0.5

_W_VENUS_ASPECT = 1.2
_W_MOON_ASPECT = 1.0
_W_CHIRON_IN_SEVENTH = 1.0
_W_VENUS_HOUSE = 0.8
_W_RULER_HOUSE = 0.8
_W_VENUS_ON_DSC = 0.8
_W_DSC_SIGN = 0.6
_W_MARS_ASPECT = 1.0
_W_MARS_IN_SEVENTH = 1.0


class PainLoopFactors(BaseModel):
    """Факторы карты, из которых выведена петля. Модель называет их вслух."""

    has_time: bool
    dsc_sign: str | None = None
    venus_sign: str | None = None
    venus_house: int | None = None
    venus_aspects: list[str] = Field(default_factory=list)
    moon_sign: str | None = None
    moon_aspects: list[str] = Field(default_factory=list)
    mars_aspects: list[str] = Field(default_factory=list)
    chiron_house: int | None = None
    ruler_seventh: str | None = None
    ruler_seventh_house: int | None = None
    venus_on_descendant: bool = False
    scores: dict[str, float] = Field(default_factory=dict)
    planet_scores: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class PainLoopResult(BaseModel):
    """Петля, точка её слома и выход — всё посчитано детерминированно."""

    methodology_version: int
    loop: str
    tagline: str
    break_point: str
    way_out: str
    leaves_first: bool  # ответ человека: чаще уходит он сам
    age: int
    factors: PainLoopFactors


RESULT_MODEL = PainLoopResult


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


def _in_sign(sign: str) -> str:
    """«в Козероге», а не «в Козерог»: формулировки уходят в ответ как есть."""
    return f"в {SIGN_RU_PREPOSITIONAL.get(sign, sign)}"


def _age(birth_date: date, today: date) -> int:
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def _add(scores: dict[str, float], loop: str, weight: float) -> None:
    scores[loop] = scores.get(loop, 0.0) + weight


def _collect_factors(chart: FullNatalChart) -> PainLoopFactors:
    """Факторы карты + баллы петель. Здесь же формулировки для промпта."""
    notes: list[str] = []
    scores: dict[str, float] = {}
    planet_scores: dict[str, float] = {}

    venus = _point(chart, "Venus")
    moon = _point(chart, "Moon")
    chiron = _point(chart, "Chiron")
    dsc_sign = _seventh_cusp_sign(chart)

    factors = PainLoopFactors(
        has_time=chart.has_time,
        dsc_sign=dsc_sign,
        venus_sign=venus.sign if venus else None,
        venus_house=venus.house if venus else None,
        moon_sign=moon.sign if moon else None,
        chiron_house=chiron.house if chiron else None,
    )

    # 1. Венера — кого человек выбирает. Главный фактор петли.
    if venus:
        notes.append(f"Венера {_in_sign(venus.sign)}" + (f", {venus.house} дом" if venus.house else ""))
        _score_hard_aspects(
            chart,
            scores,
            planet_scores,
            point_name="Venus",
            point_ru="Венера",
            table=_VENUS_ASPECT_LOOPS,
            weight=_W_VENUS_ASPECT,
            bucket=factors.venus_aspects,
            notes=notes,
        )
        if venus.house in _HOUSE_LOOPS:
            _add(scores, _HOUSE_LOOPS[venus.house], _W_VENUS_HOUSE)

    # 2. Луна — как человек привык чувствовать себя любимым.
    if moon:
        notes.append(f"Луна {_in_sign(moon.sign)}" + (f", {moon.house} дом" if moon.house else ""))
        _score_hard_aspects(
            chart,
            scores,
            planet_scores,
            point_name="Moon",
            point_ru="Луна",
            table=_MOON_ASPECT_LOOPS,
            weight=_W_MOON_ASPECT,
            bucket=factors.moon_aspects,
            notes=notes,
        )

    # 3. Венера на десценденте: аспект к ASC в оппозиции — это и есть DSC.
    if any(other == "Ascendant" and aspect == "оппозиция" for other, aspect in _aspects_with(chart, "Venus")):
        factors.venus_on_descendant = True
        _add(scores, LOOP_MERGE, _W_VENUS_ON_DSC)
        notes.append("Венера на десценденте — жизнь через партнёра")

    # 4. Хирон в 7 доме: больное место ровно там, где партнёрство.
    if chiron and chiron.house == 7:
        _add(scores, LOOP_PATIENCE, _W_CHIRON_IN_SEVENTH)
        planet_scores["Chiron"] = planet_scores.get("Chiron", 0.0) + _W_CHIRON_IN_SEVENTH
        notes.append("Хирон в 7 доме — самое больное место совпало с темой отношений")

    # 5. Управитель 7 дома по дому — где тема любви проживается.
    ruler = _ruler_point(chart, dsc_sign)
    if ruler is not None:
        factors.ruler_seventh = ruler.name_ru
        factors.ruler_seventh_house = ruler.house
        notes.append(
            f"управитель 7 дома — {ruler.name_ru} {_in_sign(ruler.sign)}"
            + (f", {ruler.house} дом" if ruler.house else ""),
        )
        if ruler.house in _HOUSE_LOOPS:
            _add(scores, _HOUSE_LOOPS[ruler.house], _W_RULER_HOUSE)

    # 6. Знак на десценденте — фон, а не приговор: вес самый лёгкий.
    if dsc_sign and dsc_sign in _DSC_SIGN_LOOPS:
        _add(scores, _DSC_SIGN_LOOPS[dsc_sign], _W_DSC_SIGN)
        notes.append(f"десцендент {_in_sign(dsc_sign)}")

    # 7. Марс в 7 доме — партнёр как соперник, отношения через борьбу.
    mars = _point(chart, "Mars")
    if mars and mars.house == 7:
        _add(scores, LOOP_FIGHT, _W_MARS_IN_SEVENTH)
        notes.append("Марс в 7 доме — партнёрство прожито как противостояние")

    # 8. Марс под тяжёлой планетой — злость, которой некуда деться.
    for other, aspect_ru in _aspects_with(chart, "Mars"):
        if other in _MARS_ASPECT_PLANETS and aspect_ru in _HARD_ASPECTS:
            _add(scores, LOOP_FIGHT, _W_MARS_ASPECT)
            planet_scores[other] = planet_scores.get(other, 0.0) + _W_MARS_ASPECT
            other_point = _point(chart, other)
            phrase = f"Марс — {aspect_ru} — {other_point.name_ru if other_point else other}"
            factors.mars_aspects.append(phrase)
            notes.append(phrase)

    factors.scores = {name: round(value, 2) for name, value in scores.items()}
    factors.planet_scores = {name: round(value, 2) for name, value in planet_scores.items()}
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
    planet_scores: dict[str, float],
    *,
    point_name: str,
    point_ru: str,
    table: dict[str, tuple[str, str | None]],
    weight: float,
    bucket: list[str],
    notes: list[str],
) -> None:
    """Жёсткие аспекты точки с тяжёлыми планетами и Хироном."""
    seen: set[str] = set()
    for other, aspect_ru in _aspects_with(chart, point_name):
        pair = table.get(other)
        if pair is None or aspect_ru not in _HARD_ASPECTS or other in seen:
            continue
        seen.add(other)
        main, shade = pair
        _add(scores, main, weight)
        if shade is not None:
            _add(scores, shade, weight * _SHADE_FACTOR)
        planet_scores[other] = planet_scores.get(other, 0.0) + weight
        other_point = _point(chart, other)
        phrase = f"{point_ru} — {aspect_ru} — {other_point.name_ru if other_point else other}"
        bucket.append(phrase)
        notes.append(phrase)


def _pick_loop(scores: dict[str, float]) -> str:
    """Петля с наибольшим баллом; ничья решается фиксированным приоритетом."""
    if not scores:
        return LOOP_PATIENCE
    best = max(scores.values())
    winners = [name for name, value in scores.items() if value == best]
    for name in _PRIORITY:
        if name in winners:
            return name
    return winners[0]


def _break_point(planet_scores: dict[str, float]) -> str:
    """Точка слома — по планете, которая петлю и задала."""
    if not planet_scores:
        return _BREAK_POINT_DEFAULT
    best = max(planet_scores.values())
    # Ничья между планетами разрешается тем же порядком, что и у точек слома:
    # словарь упорядочен, и первый совпавший выигрывает — результат стабилен.
    for planet, description in BREAK_POINT_BY_PLANET.items():
        if planet_scores.get(planet) == best:
            return description
    return _BREAK_POINT_DEFAULT


def compute(
    chart: FullNatalChart,
    *,
    birth_date: date,
    calibration: bool,
    today: date | None = None,
) -> PainLoopResult:
    """Петля, точка её слома и выход из круга."""
    today = today or date.today()
    factors = _collect_factors(chart)
    loop = _pick_loop(factors.scores)
    return PainLoopResult(
        methodology_version=METHODOLOGY_VERSION,
        loop=loop,
        tagline=LOOP_TAGLINE[loop],
        break_point=_break_point(factors.planet_scores),
        way_out=LOOP_WAY_OUT[loop],
        leaves_first=calibration,
        age=_age(birth_date, today),
        factors=factors,
    )


def render_card(result: PainLoopResult) -> bytes:
    """Карточка продукта: название петли крупно."""
    from astra.ask.card import render_card as draw

    return draw(
        hero=result.loop,
        label="твоя петля\nв отношениях",
        footnote=result.tagline,
    )
