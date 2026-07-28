"""«Сколько судьбоносных партнёров?» — детерминированный расчёт двух чисел.

Судьбоносный = поворотный союз, после которого человек другой. Брак не
обязателен: считаем не штампы, а истории, которые меняют жизнь.

Число считает этот модуль, а не LLM. Причина простая: карта одна, значит и
ответ должен быть один — иначе на повторной покупке модель выдаст другую
цифру и доверие к продукту закончится. LLM получает готовые числа и факторы
и только объясняет их.

Метод:
1. «Сколько всего за жизнь» — вес по факторам 7 дома, его управителя и Венеры.
   Фиксированные знаки и Сатурн сжимают к одному союзу, мутабельные знаки,
   Уран и Юпитер размножают.
2. «Сколько уже было / впереди» — окна активации партнёрства (windows.py):
   транзиты Сатурна, Юпитера и Урана к десценденту, Венере и управителю 7.
3. Калибровка ответом человека «сейчас в отношениях или нет».

Версия метода фиксируется в METHODOLOGY_VERSION и кладётся в БД вместе с
ответом: если правила изменятся, старые ответы останутся объяснимыми.
"""

from __future__ import annotations

from datetime import date

from astra.ask.schemas import (
    FatedPartnersFactors,
    FatedPartnersResult,
    PartnershipWindow,
)
from astra.ask.windows import (
    MIN_AGE,
    STRONG_WEIGHT,
    find_partnership_windows,
    merge_overlapping,
)
from astra.astro.constants import (
    DOUBLE_BODIED_SIGNS,
    SIGN_RU_TO_CLASSIC_RULER,
    SIGN_RU_TO_MODALITY,
)
from astra.astro.schemas import ChartPoint, FullNatalChart

METHODOLOGY_VERSION = 1

_MIN_TOTAL = 1
_MAX_TOTAL = 4

# Порог счёта → сколько судьбоносных союзов за жизнь. Пороги подобраны по
# распределению счёта на выборке карт: одна большая история — редкость (~15%),
# четыре — тоже (~15%), большинство людей живёт с двумя-тремя.
_TOTAL_THRESHOLDS: tuple[tuple[float, int], ...] = (
    (-0.9, 1),
    (0.5, 2),
    (1.8, 3),
)

# Модальность знака на десценденте: фиксированный держит одного, мутабельный дробит.
_MODALITY_SCORE: dict[str, float] = {
    "фиксированный": -1.0,
    "кардинальный": 0.0,
    "мутабельный": 1.0,
}

_DOUBLE_BODIED_SCORE = 0.5
_PLANETS_IN_SEVENTH_SCORE: dict[int, float] = {0: 0.0, 1: 0.3, 2: 0.6}
_PLANETS_IN_SEVENTH_MANY = 1.0

# Аспекты к управителю 7 дома и к Венере: кто сжимает, кто размножает.
_ASPECT_SCORE: dict[str, float] = {
    "Saturn": -0.7,
    "Uranus": 0.6,
    "Jupiter": 0.3,
}

# Потолок «уже было» по возрасту: в 24 года трёх поворотных союзов не бывает,
# сколько бы окон ни насчитали транзиты.
_MAX_PAST_BY_AGE: tuple[tuple[int, int], ...] = (
    (22, 1),
    (28, 2),
    (35, 3),
)
_VENUS_RETROGRADE_SCORE = 0.3
_NODE_IN_SEVENTH_SCORE = 0.3
_NODE_IN_FIRST_SCORE = 0.2

# Без времени рождения десцендента нет — модальность берём по Венере, вполсилы.
_NO_TIME_MODALITY_FACTOR = 0.5

_PERSONAL_POINTS = ("Sun", "Moon", "Mercury", "Venus", "Mars")


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


def _descendant_lon(chart: FullNatalChart) -> float | None:
    if not chart.has_time or chart.asc is None:
        return None
    return (chart.asc.lon + 180.0) % 360.0


def _age(birth_date: date, today: date) -> int:
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def _collect_factors(chart: FullNatalChart) -> FatedPartnersFactors:
    """Факторы карты + их вклад в счёт. Здесь же — формулировки для промпта."""
    notes: list[str] = []
    score = 0.0

    venus = _point(chart, "Venus")
    dsc_sign = _seventh_cusp_sign(chart)

    factors = FatedPartnersFactors(
        has_time=chart.has_time,
        dsc_sign=dsc_sign,
        dsc_modality=SIGN_RU_TO_MODALITY.get(dsc_sign) if dsc_sign else None,
        venus_sign=venus.sign if venus else None,
        venus_modality=venus.modality if venus else None,
        venus_retrograde=bool(venus and venus.retrograde),
    )

    # 1. Знак на десценденте (без времени — Венера вполсилы).
    if factors.dsc_modality:
        modality_score = _MODALITY_SCORE.get(factors.dsc_modality, 0.0)
        score += modality_score
        notes.append(f"десцендент в знаке {dsc_sign} ({factors.dsc_modality})")
        if dsc_sign in DOUBLE_BODIED_SIGNS:
            factors.double_bodied_dsc = True
            score += _DOUBLE_BODIED_SCORE
            notes.append(f"{dsc_sign} — двойной знак на десценденте")
    elif factors.venus_modality:
        score += _MODALITY_SCORE.get(factors.venus_modality, 0.0) * _NO_TIME_MODALITY_FACTOR
        notes.append(
            f"времени рождения нет: считаем по Венере в {factors.venus_sign} "
            f"({factors.venus_modality}), без домов",
        )

    # 2. Планеты в 7 доме.
    if chart.has_time:
        in_seventh = [p.name_ru for p in chart.points if p.house == 7 and p.name in _PERSONAL_POINTS]
        factors.planets_in_seventh = in_seventh
        count = len(in_seventh)
        score += _PLANETS_IN_SEVENTH_SCORE.get(count, _PLANETS_IN_SEVENTH_MANY)
        if in_seventh:
            notes.append("в 7 доме: " + ", ".join(in_seventh))

    # 3. Управитель 7 дома: знак и аспекты.
    if dsc_sign:
        ruler = SIGN_RU_TO_CLASSIC_RULER.get(dsc_sign)
        ruler_point = _point(chart, ruler) if ruler else None
        if ruler_point:
            factors.ruler_seventh = ruler_point.name_ru
            factors.ruler_seventh_sign = ruler_point.sign
            factors.ruler_seventh_modality = ruler_point.modality
            if ruler_point.modality == "мутабельный":
                score += 0.5
            elif ruler_point.modality == "фиксированный":
                score -= 0.5
            notes.append(
                f"управитель 7 дома — {ruler_point.name_ru} в {ruler_point.sign}"
                + (f", {ruler_point.house} дом" if ruler_point.house else ""),
            )
            score += _score_aspects(
                chart,
                point_name=ruler_point.name,
                point_ru=ruler_point.name_ru,
                bucket=factors.ruler_seventh_aspects,
                notes=notes,
            )

    # 4. Венера: аспекты и ретроградность.
    if venus:
        score += _score_aspects(
            chart,
            point_name="Venus",
            point_ru="Венера",
            bucket=factors.venus_aspects,
            notes=notes,
        )
        if venus.retrograde:
            score += _VENUS_RETROGRADE_SCORE
            notes.append("Венера ретроградная — истории возвращаются")

    # 5. Северный узел: партнёрство как задача жизни.
    node = _point(chart, "True_North_Lunar_Node")
    if node and node.house:
        factors.north_node_house = node.house
        if node.house == 7:
            score += _NODE_IN_SEVENTH_SCORE
            notes.append("северный узел в 7 доме — партнёрство как задача жизни")
        elif node.house == 1:
            score += _NODE_IN_FIRST_SCORE
            notes.append("северный узел в 1 доме — путь через себя, а не через союз")

    factors.score = round(score, 2)
    factors.notes = notes
    return factors


def _score_aspects(
    chart: FullNatalChart,
    *,
    point_name: str,
    point_ru: str,
    bucket: list[str],
    notes: list[str],
) -> float:
    """Вклад аспектов точки с Сатурном, Ураном и Юпитером."""
    score = 0.0
    seen: set[str] = set()
    for other, aspect_ru in _aspects_with(chart, point_name):
        weight = _ASPECT_SCORE.get(other)
        if weight is None or other in seen or other == point_name:
            continue
        seen.add(other)
        score += weight
        other_point = _point(chart, other)
        other_ru = other_point.name_ru if other_point else other
        phrase = f"{point_ru} — {aspect_ru} — {other_ru}"
        bucket.append(phrase)
        notes.append(phrase)
    return score


def _split_past_future(
    total: int,
    *,
    past_count: int,
    future_count: int,
    age: int,
) -> tuple[int, int]:
    """Разложить общее число на прожитое и предстоящее по доле окон."""
    windows_total = past_count + future_count
    if windows_total == 0:
        return 0, total
    share = past_count / windows_total
    past = min(round(total * share), total, _max_past_for_age(age), past_count)
    return past, total - past


def _max_past_for_age(age: int) -> int:
    for boundary, limit in _MAX_PAST_BY_AGE:
        if age < boundary:
            return limit
    return _MAX_TOTAL


def _total_from_score(score: float) -> int:
    for boundary, total in _TOTAL_THRESHOLDS:
        if score <= boundary:
            return total
    return _MAX_TOTAL


def _targets(chart: FullNatalChart) -> dict[str, float]:
    """Точки карты, по которым ищем окна партнёрства."""
    targets: dict[str, float] = {}
    dsc = _descendant_lon(chart)
    if dsc is not None:
        targets["десцендент"] = dsc
    venus = _point(chart, "Venus")
    if venus:
        targets["Венера"] = venus.lon
    dsc_sign = _seventh_cusp_sign(chart)
    ruler = SIGN_RU_TO_CLASSIC_RULER.get(dsc_sign) if dsc_sign else None
    ruler_point = _point(chart, ruler) if ruler else None
    if ruler_point and ruler_point.name != "Venus":
        targets["управитель 7 дома"] = ruler_point.lon
    return targets


def compute_fated_partners(
    chart: FullNatalChart,
    *,
    birth_date: date,
    in_relationship: bool,
    today: date | None = None,
) -> FatedPartnersResult:
    """Два числа — сколько судьбоносных союзов уже было и сколько впереди."""
    today = today or date.today()
    age = _age(birth_date, today)

    factors = _collect_factors(chart)
    total = _total_from_score(factors.score)

    windows = merge_overlapping(
        find_partnership_windows(_targets(chart), birth_date=birth_date, today=today),
    )
    strong = [w for w in windows if w.weight >= STRONG_WEIGHT and w.age >= MIN_AGE]
    past_windows = [w for w in strong if w.end < today]
    future_windows = [w for w in strong if w.end >= today]

    # Делим число не «сколько окон прошло», а по доле прожитых окон: иначе у
    # человека за сорок всё всегда оказывается позади, и вопрос «сколько
    # впереди» теряет смысл. Горизонт будущего — 15 лет (windows.FUTURE_YEARS).
    past, future = _split_past_future(
        total,
        past_count=len(past_windows),
        future_count=len(future_windows),
        age=age,
    )

    # Человек в отношениях: хотя бы одна история уже случилась — это он и есть.
    if in_relationship and past == 0:
        past = 1
        future = min(max(total - 1, 0), len(future_windows))

    # Свободному человеку не говорим «всё позади», если карта показывает
    # открытое окно впереди. Общее число при этом не раздуваем — переносим
    # одну историю из прошлого в будущее, а не дарим лишнюю.
    if not in_relationship and future == 0 and future_windows and past > 0:
        past -= 1
        future = 1

    total = past + future
    if total == 0:
        total, past, future = 1, 0, 1

    return FatedPartnersResult(
        methodology_version=METHODOLOGY_VERSION,
        total=total,
        past=past,
        future=future,
        age=age,
        in_relationship=in_relationship,
        factors=factors,
        windows_past=_trim(past_windows, past),
        windows_future=_trim(future_windows, future),
    )


def _trim(windows: list[PartnershipWindow], limit: int) -> list[PartnershipWindow]:
    """Оставить самые весомые окна, но в хронологическом порядке."""
    if limit <= 0:
        return []
    strongest = sorted(windows, key=lambda w: (-w.weight, w.peak))[:limit]
    return sorted(strongest, key=lambda w: w.peak)
