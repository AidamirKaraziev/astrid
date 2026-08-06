"""Поиск места по тому, что человек набрал.

## Правило ранжирования

Сначала **совпадение**, население — в последнюю очередь. Раньше было
наоборот, и на «Красноярск» первым приходило село Красноярск Оренбургской
области, а на «Москва» — деревня Москва в Тверской: настоящие города
проигрывали, потому что у них в поле поиска сотни синонимов и похожесть
размывалась.

Ступени, сверху вниз:

1. точное совпадение названия;
2. название начинается с запроса;
3. похоже название;
4. похоже что-то из синонимов, региона или страны.

Внутри ступени — величина похожести, и только при полной ничьей население.

## Опечатки и алфавит

Каждая ступень сравнивает и по-русски, и по латинскому ключу. «Зябриково»
находит `Zyabrikovo`, у которого русского имени в источнике нет вовсе, а
`Moskva` находит Москву.

Опечатки ловит нечёткое сравнение (`pg_trgm`). Если строгий проход не дал
ничего, второй идёт с пониженным порогом: «Краснадар» должен приводить к
Краснодару, а не в тупик.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from uuid import UUID

from sqlalchemy import ColumnElement, Float, case, cast, func, literal, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from astra.places.models import Place
from astra.places.query import PlaceQuery, parse_place_query

# Порог похожести pg_trgm для обычного поиска. Штатное значение базы — 0.3;
# берём ниже, потому что деревня с длинным названием иначе не находится по
# короткому запросу.
SIMILARITY_THRESHOLD = 0.25
# Второй проход, когда строгий не нашёл ничего: тут уже явная опечатка, и
# лучше показать пять похожих вариантов, чем «ничего не нашла».
FUZZY_THRESHOLD = 0.12
# Насколько текст региона из запроса должен совпасть с настоящим названием,
# чтобы считать, что человек имел в виду именно его.
REGION_MATCH = 0.35

# Ступени совпадения — чем больше, тем выше в списке.
_RANK_EXACT = 5
_RANK_EXACT_SYNONYM = 4
_RANK_PREFIX = 3
_RANK_NAME_SIMILAR = 2
_RANK_TEXT_SIMILAR = 1

# Штраф за каждую букву разницы в длине названия. Подобран так, чтобы
# «Краснодар» обходил «Красну» по запросу «Краснадар», но не перебивал
# честное совпадение: три буквы разницы стоят меньше одной ступени.
_LENGTH_PENALTY = 0.03


@dataclass(frozen=True)
class RegionHit:
    """Регион и сколько в нём мест с таким названием."""

    admin1_name: str | None
    country_name: str | None
    count: int

    @property
    def title(self) -> str:
        region = self.admin1_name or self.country_name or "без региона"
        if self.admin1_name and self.country_name and self.country_name != "Россия":
            return f"{region}, {self.country_name}"
        return region


async def get_place_by_id(session: AsyncSession, place_id: UUID) -> Place | None:
    result = await session.execute(select(Place).where(Place.id == place_id))
    return result.scalar_one_or_none()


async def get_place_by_geoname_id(session: AsyncSession, geoname_id: int) -> Place | None:
    result = await session.execute(select(Place).where(Place.geoname_id == geoname_id))
    return result.scalar_one_or_none()


async def count_places(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(Place))
    return int(result.scalar_one())


# --------------------------------------------------------------------------
# Сборка условий поиска
# --------------------------------------------------------------------------


def _similarity(column: ColumnElement[str], value: str) -> ColumnElement[float]:
    return cast(func.similarity(column, value), Float)


class MatchLevel(IntEnum):
    """Насколько широко смотрим. Каждая ступень включает предыдущие."""

    EXACT = 1  # название совпало буква в букву
    PREFIX = 2  # название начинается с запроса
    NAME = 3  # название похоже
    TEXT = 4  # похож синоним, регион или страна
    TYPO = 5  # то же, но с расчётом на опечатку


def _matches(query: PlaceQuery, level: MatchLevel) -> ColumnElement[bool]:
    """Условие отбора для ступени.

    Ступени нужны не ради скорости (хотя и ради неё тоже): без них счётчик
    совпадений раздувается нечётким хвостом. По запросу «Красное» находилось
    3937 мест в 177 регионах вместо 171 в 62 — и первый шаг выбора, где
    человек указывает регион, терял всякий смысл.

    Нечёткое сравнение делается оператором `%`, а не функцией `similarity`:
    только оператор ходит в GIN-индекс. С функцией каждый запрос перебирал
    все 337 тысяч строк и отвечал больше секунды. Порог оператору задаётся
    настройкой сессии (`_set_threshold`).
    """
    conditions: list[ColumnElement[bool]] = [
        Place.name_normalized == query.name,
        _exact_synonym(query),
    ]
    if query.name_latin:
        conditions.append(Place.name_latin == query.name_latin)

    if level >= MatchLevel.PREFIX:
        conditions.append(Place.name_normalized.like(query.prefix))
        if query.name_latin:
            conditions.append(Place.name_latin.like(query.prefix_latin))

    if level >= MatchLevel.NAME:
        conditions.append(Place.name_normalized.op("%")(query.name))
        if query.name_latin:
            conditions.append(Place.name_latin.op("%")(query.name_latin))

    if level >= MatchLevel.TEXT:
        conditions.append(Place.search_text.op("%")(query.name))
        if query.name_latin:
            conditions.append(Place.search_latin.op("%")(query.name_latin))

    return or_(*conditions)


def _exact_synonym(query: PlaceQuery) -> ColumnElement[bool]:
    """Запрос совпал с одним из имён места целиком.

    Ради людей, родившихся до девяносто первого: «Ленинград» и «Свердловск» —
    это Санкт-Петербург и Екатеринбург, но названиями они больше не являются
    и основным именем стать не могут. Зато посёлки с такими названиями
    существуют до сих пор, и без этого условия человек, набравший «Ленинград»,
    получал пять деревень Туркменистана и Таджикистана, а своего города в
    списке не видел вовсе.

    Сравнение идёт по отдельному полю с разделителями, а не по общему тексту
    поиска: там «Красное» совпадало бы со словом внутри «Красного Эха», и
    счётчик тёзок раздувался со 172 до 310.
    """
    return Place.search_names.like(f"%|{query.name}|%")


def _threshold_for(level: MatchLevel) -> float:
    return FUZZY_THRESHOLD if level is MatchLevel.TYPO else SIMILARITY_THRESHOLD


async def _set_threshold(session: AsyncSession, threshold: float) -> None:
    """Порог для оператора `%` на время текущей транзакции."""
    await session.execute(text(f"SET LOCAL pg_trgm.similarity_threshold = {threshold:.3f}"))


def _rank(query: PlaceQuery) -> ColumnElement[int]:
    """Ступень совпадения: точное → начало → похожее название → похожий текст."""
    exact = [Place.name_normalized == query.name]
    prefix = [Place.name_normalized.like(query.prefix)]
    similar = [_similarity(Place.name_normalized, query.name) > 0]
    if query.name_latin:
        exact.append(Place.name_latin == query.name_latin)
        prefix.append(Place.name_latin.like(query.prefix_latin))
        similar.append(_similarity(Place.name_latin, query.name_latin) > 0)

    return case(
        (or_(*exact), literal(_RANK_EXACT)),
        (_exact_synonym(query), literal(_RANK_EXACT_SYNONYM)),
        (or_(*prefix), literal(_RANK_PREFIX)),
        (or_(*similar), literal(_RANK_NAME_SIMILAR)),
        else_=literal(_RANK_TEXT_SIMILAR),
    )


def _name_similarity(query: PlaceQuery) -> ColumnElement[float]:
    """Насколько похоже само название — главный признак внутри ступени.

    Из похожести вычитается разница длин. Без этого короткие названия всегда
    выигрывают у длинных: у «Красны» с запросом «Краснадар» общих трёхбуквенных
    кусочков доля выше, чем у «Краснодара», просто потому что слово короче, —
    и человек с опечаткой попадал в село Ивано-Франковской области вместо
    краевого центра.
    """
    russian = _similarity(Place.name_normalized, query.name)
    score = russian
    if query.name_latin:
        score = func.greatest(russian, _similarity(Place.name_latin, query.name_latin))
    length_gap = func.abs(func.char_length(Place.name_normalized) - len(query.name))
    return score - _LENGTH_PENALTY * cast(length_gap, Float)


def _region_bonus(query: PlaceQuery) -> ColumnElement[int]:
    """Регион из запроса поднимает свои места, но не отсекает остальные.

    Не фильтром, а бонусом: человек может написать «Советское, Кубань» или
    ошибиться в регионе, и терять из-за этого его место рождения нельзя.
    """
    if not query.region_key:
        return literal(0)
    return case((_region_matches(query), literal(1)), else_=literal(0))


def _region_matches(query: PlaceQuery) -> ColumnElement[bool]:
    """Регион из запроса совпал с настоящим названием региона."""
    key = query.region_key or ""
    return _similarity(func.coalesce(Place.admin1_name, ""), key) >= REGION_MATCH


def _order_by(query: PlaceQuery) -> list[ColumnElement]:
    return [
        # Регион важнее степени совпадения: человек, написавший «село
        # советское краснодарский край», не должен получить первой строкой
        # точную тёзку из Киргизии.
        _region_bonus(query).desc(),
        _rank(query).desc(),
        _name_similarity(query).desc(),
        # Население — последний аргумент, а не первый: из двух одинаково
        # подходящих «Красных» разумнее показать сначала то, где живут люди.
        Place.population.desc(),
        Place.geoname_id.asc(),  # стабильный порядок между запросами
    ]


# --------------------------------------------------------------------------
# Поиск
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PreparedSearch:
    """Запрос вместе с проходом, на котором он что-то нашёл.

    Проход фиксируется один раз и дальше используется всеми выборками. Иначе
    список регионов считался бы по одним правилам, а список мест по другим, и
    человек, выбрав «Тверская область · 10», получил бы там три места.
    """

    query: PlaceQuery
    level: MatchLevel
    total: int
    country_code: str | None = None


def _scoped(statement, search: PreparedSearch):
    if search.country_code:
        return statement.where(Place.country_code == search.country_code)
    return statement


async def prepare_search(
    session: AsyncSession,
    query: str,
    *,
    country_code: str | None = None,
) -> PreparedSearch | None:
    """Разобрать запрос и найти первый проход, на котором есть результаты."""
    parsed = parse_place_query(query)
    if not parsed.is_searchable:
        return None

    async def total_at(level: MatchLevel, *, inside_region: bool) -> int:
        await _set_threshold(session, _threshold_for(level))
        statement = select(func.count()).select_from(Place).where(_matches(parsed, level))
        if country_code:
            statement = statement.where(Place.country_code == country_code)
        if inside_region and parsed.region_key:
            statement = statement.where(_region_matches(parsed))
        return int((await session.execute(statement)).scalar_one())

    # Человек назвал регион — расширяемся до тех пор, пока в этом регионе
    # что-нибудь не найдётся. Иначе «село советское краснодарский край»
    # останавливается на точной тёзке из Киргизии и до Кубани не доходит:
    # там есть «Советский» и «Советская», но «Советского» нет.
    levels = list(MatchLevel)
    if parsed.region_key:
        for level in levels:
            if await total_at(level, inside_region=True):
                total = await total_at(level, inside_region=False)
                return PreparedSearch(
                    query=parsed,
                    level=level,
                    total=total,
                    country_code=country_code,
                )

    for level in levels:
        total = await total_at(level, inside_region=False)
        if total:
            return PreparedSearch(
                query=parsed,
                level=level,
                total=total,
                country_code=country_code,
            )
    return None


async def places_for(
    session: AsyncSession,
    search: PreparedSearch,
    *,
    limit: int = 5,
    offset: int = 0,
    region: str | None = None,
) -> list[Place]:
    """Места по подготовленному запросу, по убыванию совпадения.

    `region` — уже выбранный человеком регион на втором шаге; здесь выдача
    ограничивается им жёстко, в отличие от региона, угаданного из текста.
    """
    await _set_threshold(session, _threshold_for(search.level))
    statement = select(Place).where(_matches(search.query, search.level))
    statement = _scoped(statement, search)
    if region is not None:
        statement = statement.where(Place.admin1_name == region)
    statement = statement.order_by(*_order_by(search.query)).limit(limit).offset(offset)
    return list((await session.execute(statement)).scalars().all())


async def regions_for(
    session: AsyncSession,
    search: PreparedSearch,
    *,
    limit: int = 8,
    offset: int = 0,
) -> list[RegionHit]:
    """Регионы, где есть подходящие места, по убыванию количества.

    Первый шаг выбора, когда тёзок много: 171 «Красное» списком бесполезно,
    62 региона — уже выбор, который человек может сделать.
    """
    await _set_threshold(session, _threshold_for(search.level))
    statement = (
        select(Place.admin1_name, Place.country_name, func.count().label("hits"))
        .where(_matches(search.query, search.level))
        .group_by(Place.admin1_name, Place.country_name)
        .order_by(func.count().desc(), Place.admin1_name.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(_scoped(statement, search))).all()
    return [RegionHit(admin1_name=row[0], country_name=row[1], count=row[2]) for row in rows]


async def count_regions_for(session: AsyncSession, search: PreparedSearch) -> int:
    await _set_threshold(session, _threshold_for(search.level))
    inner = (
        select(Place.admin1_name, Place.country_name)
        .where(_matches(search.query, search.level))
        .group_by(Place.admin1_name, Place.country_name)
    )
    inner = _scoped(inner, search)
    statement = select(func.count()).select_from(inner.subquery())
    return int((await session.execute(statement)).scalar_one())


async def search_places(
    session: AsyncSession,
    query: str,
    *,
    limit: int = 5,
    offset: int = 0,
    region: str | None = None,
    country_code: str | None = None,
) -> list[Place]:
    """Простой вход для одиночного поиска: разобрать запрос и отдать места."""
    search = await prepare_search(session, query, country_code=country_code)
    if search is None:
        return []
    return await places_for(session, search, limit=limit, offset=offset, region=region)
