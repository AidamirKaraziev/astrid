"""«Будут ли у меня дети?» — тема родительства в карте и лучшие окна.

Продукт сознательно **не отвечает «нет»**. Астрология не видит фертильность, а
фраза «детей не будет» — это утверждение о теле человека, из-за которого он
может принять реальное решение о своей жизни или здоровье. Поэтому вопрос
читается как «что говорит карта о теме родительства»: какой у неё сценарий,
сколько детей она показывает (минимум один), когда открываются лучшие окна.

Как и везде в разделе, всё считает Python: сценарий, число и окна. LLM их
объясняет и не может ни отменить, ни добавить своих.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from astra.ask.windows import TransitWindow, find_windows, merge_overlapping, window_period
from astra.astro.constants import SIGN_RU_TO_CLASSIC_RULER
from astra.astro.schemas import ChartPoint, FullNatalChart

METHODOLOGY_VERSION = 1

class ChildrenFactors(BaseModel):
    """Факторы темы детей. Идут в промпт как есть и называются в ответе вслух."""

    has_time: bool
    fifth_sign: str | None = None
    fifth_fertility: str | None = None  # плодородный / нейтральный / сухой
    planets_in_fifth: list[str] = Field(default_factory=list)
    ruler_fifth: str | None = None
    ruler_fifth_sign: str | None = None
    ruler_fifth_house: int | None = None
    ruler_fifth_aspects: list[str] = Field(default_factory=list)
    moon_sign: str | None = None
    moon_house: int | None = None
    moon_aspects: list[str] = Field(default_factory=list)
    jupiter_aspects: list[str] = Field(default_factory=list)
    north_node_house: int | None = None
    score: float = 0.0
    notes: list[str] = Field(default_factory=list)


class ChildrenResult(BaseModel):
    """Тема родительства в карте: сценарий, сколько показывает карта, окна.

    Вердикта «детей не будет» здесь нет и быть не может: карта не видит
    фертильность, а такой ответ человек может принять за медицинский.
    """

    methodology_version: int
    theme: str  # ранняя / поздняя / через усилие / центральная / спокойная
    count_hint: int  # сколько показывает карта, минимум 1
    age: int
    has_children: bool  # ответ человека перед покупкой
    parenting_age_passed: bool  # окна деторождения уже позади — тема звучит иначе
    factors: ChildrenFactors
    windows: list[TransitWindow] = Field(default_factory=list)  # лучшие впереди
    best_window: TransitWindow | None = None


RESULT_MODEL = ChildrenResult

# Окна деторождения дальше этого возраста не обещаем: тема переходит в другую
# фазу (внуки, приёмные дети, дети в жизни через других людей).
MAX_PARENTING_AGE = 47
_MIN_WINDOW_AGE = 18
_MAX_WINDOWS = 3

THEME_EARLY = "ранняя"
THEME_LATE = "поздняя"
THEME_EFFORT = "через усилие"
THEME_CENTRAL = "центральная"
THEME_CALM = "спокойная"

# Классика: плодородные знаки — водные, сухие — Близнецы, Лев, Дева.
_FERTILE_SIGNS = frozenset({"Рак", "Скорпион", "Рыбы"})
_BARREN_SIGNS = frozenset({"Близнецы", "Лев", "Дева"})

_FERTILE = "плодородный"
_NEUTRAL = "нейтральный"
_BARREN = "сухой"

_PERSONAL_POINTS = ("Sun", "Moon", "Mercury", "Venus", "Mars")
_HELPERS = ("Jupiter", "Venus", "Moon")
_HARD_ASPECTS = frozenset({"соединение", "квадрат", "оппозиция"})

# Веса окон: Юпитер к 5 дому — главный «плодородный» транзит, Сатурн даёт
# поздние и обдуманные окна, Уран — внезапные повороты темы.
_WINDOW_WEIGHTS: dict[tuple[str, str], float] = {
    ("Юпитер", "5 дом"): 1.0,
    ("Юпитер", "Луна"): 0.9,
    ("Юпитер", "управитель 5 дома"): 0.8,
    ("Сатурн", "5 дом"): 0.6,
    ("Сатурн", "Луна"): 0.5,
    ("Уран", "Луна"): 0.5,
    ("Уран", "5 дом"): 0.5,
}


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


def _fifth_cusp_lon(chart: FullNatalChart) -> float | None:
    if not chart.has_time or not chart.houses:
        return None
    cusp = next((h for h in chart.houses if h.number == 5), None)
    return cusp.lon if cusp else None


def _fertility(sign: str | None) -> str | None:
    if sign is None:
        return None
    if sign in _FERTILE_SIGNS:
        return _FERTILE
    if sign in _BARREN_SIGNS:
        return _BARREN
    return _NEUTRAL


def _age(birth_date: date, today: date) -> int:
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def _collect_factors(chart: FullNatalChart) -> tuple[ChildrenFactors, dict[str, bool]]:
    """Факторы + флаги, из которых складывается сценарий темы."""
    notes: list[str] = []
    score = 0.0
    flags = {"saturn": False, "hard": False, "helper": False, "focus": False}

    fifth_sign = _fifth_cusp_sign(chart)
    moon = _point(chart, "Moon")
    factors = ChildrenFactors(
        has_time=chart.has_time,
        fifth_sign=fifth_sign,
        fifth_fertility=_fertility(fifth_sign),
        moon_sign=moon.sign if moon else None,
        moon_house=moon.house if moon else None,
    )

    if fifth_sign:
        notes.append(f"5 дом в знаке {fifth_sign} ({factors.fifth_fertility})")
        if factors.fifth_fertility == _FERTILE:
            score += 1.0
        elif factors.fifth_fertility == _BARREN:
            score -= 0.7

    if chart.has_time:
        in_fifth = [p for p in chart.points if p.house == 5 and p.name in _PERSONAL_POINTS]
        planets_fifth = [p for p in chart.points if p.house == 5]
        factors.planets_in_fifth = [p.name_ru for p in planets_fifth]
        if planets_fifth:
            notes.append("в 5 доме: " + ", ".join(factors.planets_in_fifth))
        if len(in_fifth) >= 2:
            flags["focus"] = True
        for point in planets_fifth:
            if point.name in _HELPERS:
                score += 0.5
                flags["helper"] = True
            if point.name == "Saturn":
                score -= 0.5
                flags["saturn"] = True
            if point.name in ("Pluto", "Chiron"):
                flags["hard"] = True

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
            score += _score_aspects(
                chart,
                point_name=ruler.name,
                point_ru=ruler.name_ru,
                bucket=factors.ruler_fifth_aspects,
                notes=notes,
                flags=flags,
            )

    if moon:
        notes.append(
            f"Луна в {moon.sign}" + (f", {moon.house} дом" if moon.house else ""),
        )
        score += _score_aspects(
            chart,
            point_name="Moon",
            point_ru="Луна",
            bucket=factors.moon_aspects,
            notes=notes,
            flags=flags,
        )

    jupiter = _point(chart, "Jupiter")
    if jupiter:
        for other, aspect_ru in _aspects_with(chart, "Jupiter"):
            if other in ("Moon", "Venus"):
                other_point = _point(chart, other)
                phrase = f"Юпитер — {aspect_ru} — {other_point.name_ru if other_point else other}"
                factors.jupiter_aspects.append(phrase)
                notes.append(phrase)
                score += 0.3
                flags["helper"] = True

    node = _point(chart, "True_North_Lunar_Node")
    if node and node.house:
        factors.north_node_house = node.house
        if node.house == 5:
            flags["focus"] = True
            score += 0.3
            notes.append("северный узел в 5 доме — тема детей и творчества как задача жизни")

    factors.score = round(score, 2)
    factors.notes = notes
    return factors, flags


def _score_aspects(
    chart: FullNatalChart,
    *,
    point_name: str,
    point_ru: str,
    bucket: list[str],
    notes: list[str],
    flags: dict[str, bool],
) -> float:
    """Аспекты точки с Юпитером, Сатурном, Плутоном и Хироном."""
    score = 0.0
    seen: set[str] = set()
    for other, aspect_ru in _aspects_with(chart, point_name):
        if other in seen:
            continue
        weight = {"Jupiter": 0.4, "Venus": 0.3, "Saturn": -0.5, "Pluto": -0.3, "Chiron": -0.3}.get(
            other,
        )
        if weight is None:
            continue
        seen.add(other)
        score += weight
        other_point = _point(chart, other)
        other_ru = other_point.name_ru if other_point else other
        phrase = f"{point_ru} — {aspect_ru} — {other_ru}"
        bucket.append(phrase)
        notes.append(phrase)
        if other == "Saturn":
            flags["saturn"] = True
        if other in ("Pluto", "Chiron") and aspect_ru in _HARD_ASPECTS:
            flags["hard"] = True
        if other in ("Jupiter", "Venus"):
            flags["helper"] = True
    return score


def _theme(flags: dict[str, bool], score: float) -> str:
    """Сценарий темы. Порядок проверок = приоритет: Сатурн важнее «лёгкости»."""
    if flags["saturn"] and flags["hard"]:
        return THEME_EFFORT
    if flags["saturn"]:
        return THEME_LATE
    if flags["focus"]:
        return THEME_CENTRAL
    if flags["helper"] and score >= 0.8:
        return THEME_EARLY
    return THEME_CALM


# Пороги счёта → сколько детей показывает карта. Подобраны по квантилям счёта
# на выборке карт: цель — 35/45/20 на одного/двоих/троих. Ноль не отдаём никогда.
_COUNT_THRESHOLDS: tuple[tuple[float, int], ...] = ((-0.2, 1), (1.1, 2))


def _count_hint(factors: ChildrenFactors) -> int:
    """Сколько детей показывает карта. Минимум один — ноль мы не отдаём."""
    for boundary, count in _COUNT_THRESHOLDS:
        if factors.score <= boundary:
            return count
    return 3


def _targets(chart: FullNatalChart) -> dict[str, float]:
    targets: dict[str, float] = {}
    fifth = _fifth_cusp_lon(chart)
    if fifth is not None:
        targets["5 дом"] = fifth
    moon = _point(chart, "Moon")
    if moon:
        targets["Луна"] = moon.lon
    fifth_sign = _fifth_cusp_sign(chart)
    ruler_name = SIGN_RU_TO_CLASSIC_RULER.get(fifth_sign) if fifth_sign else None
    ruler = _point(chart, ruler_name) if ruler_name else None
    if ruler and ruler.name != "Moon":
        targets["управитель 5 дома"] = ruler.lon
    return targets


def compute(
    chart: FullNatalChart,
    *,
    birth_date: date,
    calibration: bool,
    today: date | None = None,
) -> ChildrenResult:
    """Тема родительства: сценарий, сколько показывает карта, лучшие окна."""
    today = today or date.today()
    age = _age(birth_date, today)

    factors, flags = _collect_factors(chart)
    theme = _theme(flags, factors.score)

    # Схлопываем пересекающиеся окна: Юпитер за год заходит в орб дважды
    # (прямым ходом и ретро) — это один период, а не два разных шанса.
    windows = merge_overlapping(
        find_windows(
            _targets(chart),
            weights=_WINDOW_WEIGHTS,
            birth_date=birth_date,
            today=today,
            min_age=_MIN_WINDOW_AGE,
            future_years=MAX_PARENTING_AGE - age if age < MAX_PARENTING_AGE else 0,
        ),
    )
    ahead = [w for w in windows if w.end >= today and w.age <= MAX_PARENTING_AGE]
    best_first = sorted(ahead, key=lambda w: (-w.weight, w.peak))[:_MAX_WINDOWS]
    best_window = best_first[0] if best_first else None

    return ChildrenResult(
        methodology_version=METHODOLOGY_VERSION,
        theme=theme,
        count_hint=_count_hint(factors),
        age=age,
        has_children=calibration,
        parenting_age_passed=age >= MAX_PARENTING_AGE,
        factors=factors,
        windows=sorted(best_first, key=lambda w: w.peak),
        best_window=best_window,
    )


def render_card(result: ChildrenResult) -> bytes:
    """Карточка продукта: годы лучшего окна крупно."""
    from astra.ask.card import render_card as draw
    from astra.llm.prompts.ask.children import count_words

    footnote = f"карта показывает {count_words(result.count_hint)}"
    if result.best_window is None:
        return draw(hero="✨", label="тема детей\nв твоей карте", footnote=footnote)
    return draw(
        hero=window_period(result.best_window),
        label="лучшее окно\nдля темы детей",
        footnote=footnote,
    )
