"""Поиск места на живом справочнике.

Мок здесь бесполезен принципиально: проверяется ранжирование, которое целиком
живёт в SQL и в данных. Поэтому — настоящий Postgres с настоящими 337 тысячами
мест.

Главная часть — приёмочный список (`places_control_list`): полторы сотни
городов пятнадцати стран, каждый обязан находиться первой строкой. Он стоит
здесь потому, что справочник ломался **молча**: «Череповец» приводил к
«Черепаново», Владикавказ лежал под именем «Буро-ГӀала», и это доехало до
людей. Список — единственное, что не даст такому повториться незамеченным.
"""

from __future__ import annotations

import pytest

from astra.places.control_list import ALL_CASES, HISTORIC_REGIONS
from astra.places import crud
from astra.places.query import parse_place_query

pytestmark = pytest.mark.usefixtures("full_catalog")


class TestControlList:
    """Города, которые обязаны находиться. Не находится — это баг."""

    @pytest.mark.parametrize(("query", "name", "country"), ALL_CASES, ids=[c[0] for c in ALL_CASES])
    async def test_city_is_the_first_hit(
        self,
        db_session,
        query: str,
        name: str,
        country: str,
    ) -> None:
        found = await crud.search_places(db_session, query, limit=1)
        assert found, f"«{query}» не находится вовсе"
        assert (found[0].name, found[0].country_name) == (name, country), (
            f"«{query}» → {found[0].display_name}"
        )

    @pytest.mark.parametrize(
        ("query", "region"),
        HISTORIC_REGIONS,
        ids=[case[0] for case in HISTORIC_REGIONS],
    )
    async def test_soviet_name_offers_the_right_region(
        self,
        db_session,
        query: str,
        region: str,
    ) -> None:
        """Родившийся до 91-го должен увидеть свою область на первом шаге."""
        search = await crud.prepare_search(db_session, query)
        assert search is not None, f"«{query}» не находится вовсе"
        regions = await crud.regions_for(db_session, search, limit=8)
        titles = [hit.admin1_name for hit in regions]
        assert region in titles, f"«{query}» не предлагает «{region}»: {titles}"


class TestRanking:
    """Сначала совпадение, население — только при ничьей."""

    async def test_capital_beats_the_village_with_the_same_name(self, db_session) -> None:
        """Деревня Москва в Тверской области больше не первая."""
        found = await crud.search_places(db_session, "Москва", limit=1)
        assert found[0].display_name == "Москва, Россия"

    async def test_exact_name_beats_bigger_city_with_similar_name(self, db_session) -> None:
        """Совпадение важнее размера: «Сокол» — это Сокол, а не Соколовское."""
        found = await crud.search_places(db_session, "Сокол", limit=1)
        assert found[0].name == "Сокол"

    async def test_district_of_a_city_is_not_a_birthplace(self, db_session) -> None:
        """Микрорайоны выкинуты из справочника: рождаются не в них."""
        found = await crud.search_places(db_session, "Санкт-Петербург", limit=5)
        assert found[0].name == "Санкт-Петербург"
        assert "Калининский" not in [place.name for place in found]


class TestTypos:
    """Опечатка не должна заканчиваться тупиком."""

    @pytest.mark.parametrize(
        ("typo", "expected"),
        [
            ("Краснадар", "Краснодар"),
            ("Черповец", "Череповец"),
            ("Владивасток", "Владивосток"),
            ("Екатиринбург", "Екатеринбург"),
        ],
    )
    async def test_typo_finds_the_city(self, db_session, typo: str, expected: str) -> None:
        found = await crud.search_places(db_session, typo, limit=1)
        assert found and found[0].name == expected

    async def test_short_name_does_not_win_by_being_short(self, db_session) -> None:
        """«Краснадар» → Краснодар, а не село Красна: коротким словам штраф."""
        found = await crud.search_places(db_session, "Краснадар", limit=1)
        assert found[0].name == "Краснодар"


class TestAlphabets:
    """Русский запрос и латинская запись должны сходиться."""

    async def test_russian_query_finds_latin_only_place(self, db_session) -> None:
        """У четверти мест СНГ русского имени в источнике нет вовсе."""
        found = await crud.search_places(db_session, "Зябриково", limit=1)
        assert found and found[0].name_latin == "zyabrikovo"

    async def test_latin_query_finds_russian_place(self, db_session) -> None:
        found = await crud.search_places(db_session, "Moskva", limit=1)
        assert found[0].display_name == "Москва, Россия"


class TestRegionInQuery:
    """Регион в запросе сужает выдачу, а не мешает ей."""

    async def test_region_wins_over_exact_namesake_elsewhere(self, db_session) -> None:
        """Тот самый случай: «село советское краснодарский край».

        Точного «Советского» на Кубани нет — есть «Советский» и «Советская».
        Раньше первой строкой приходила точная тёзка из Киргизии.
        """
        found = await crud.search_places(
            db_session,
            "село советское краснодарский край",
            limit=3,
        )
        assert found
        assert all(place.admin1_name == "Краснодарский край" for place in found)

    async def test_region_narrows_namesakes(self, db_session) -> None:
        found = await crud.search_places(db_session, "Красное Липецкая область", limit=3)
        assert found
        assert all(place.admin1_name == "Липецкая область" for place in found)

    async def test_settlement_word_is_ignored(self, db_session) -> None:
        with_word = await crud.search_places(db_session, "город Казань", limit=1)
        without = await crud.search_places(db_session, "Казань", limit=1)
        assert with_word[0].id == without[0].id


class TestTwoStepPicking:
    """Тёзки: сначала регион, потом место с ориентиром."""

    async def test_namesakes_are_grouped_by_region(self, db_session) -> None:
        search = await crud.prepare_search(db_session, "Красное")
        assert search is not None
        assert search.total > 100, "«Красных» в СНГ должно быть много"

        regions = await crud.regions_for(db_session, search, limit=5)
        assert len(regions) == 5
        # По убыванию количества: человеку показываем сначала те регионы,
        # где вероятность найти своё место выше.
        assert [region.count for region in regions] == sorted(
            (region.count for region in regions),
            reverse=True,
        )

    async def test_places_inside_region_are_distinguishable(self, db_session) -> None:
        """Ради этого и считался ориентир: строки не должны повторяться."""
        search = await crud.prepare_search(db_session, "Красное")
        assert search is not None
        places = await crud.places_for(
            db_session,
            search,
            limit=5,
            region="Тверская область",
        )
        assert len(places) >= 3
        labels = [(place.name, place.nearest_city, place.nearest_city_km) for place in places]
        assert len(set(labels)) == len(labels), f"неразличимые строки: {labels}"

    async def test_region_counts_match_the_place_list(self, db_session) -> None:
        """Счётчик на кнопке региона не должен врать."""
        search = await crud.prepare_search(db_session, "Ивановка")
        assert search is not None
        region = (await crud.regions_for(db_session, search, limit=1))[0]
        places = await crud.places_for(
            db_session,
            search,
            limit=region.count + 5,
            region=region.admin1_name,
        )
        assert len(places) == region.count


class TestEdges:
    async def test_one_letter_finds_nothing(self, db_session) -> None:
        assert await crud.search_places(db_session, "М") == []

    async def test_empty_query_finds_nothing(self, db_session) -> None:
        assert await crud.search_places(db_session, "   ") == []

    async def test_search_is_stable_between_calls(self, db_session) -> None:
        first = await crud.search_places(db_session, "Ивановка", limit=5)
        second = await crud.search_places(db_session, "Ивановка", limit=5)
        assert [place.id for place in first] == [place.id for place in second]


class TestQueryParsing:
    """Разбор строки — без базы, поэтому быстрый и подробный."""

    @pytest.mark.parametrize(
        ("raw", "name", "region"),
        [
            ("село советское краснодарский край", "советское", "краснодарский край"),
            ("Советское, Краснодарский край", "советское", "краснодарский край"),
            ("г. Москва", "москва", None),
            ("Красное Липецкая область", "красное", "липецкая область"),
            ("Казань, Республика Татарстан", "казань", "республика татарстан"),
            ("ст-ца Калининская", "калининская", None),
            ("Москва", "москва", None),
        ],
    )
    def test_splits_name_and_region(self, raw: str, name: str, region: str | None) -> None:
        parsed = parse_place_query(raw)
        assert (parsed.name, parsed.region) == (name, region)

    def test_region_key_drops_the_marker_word(self) -> None:
        """«Липецкая» и «Львовская» похожи на 0,13, а с «областью» — на 0,46."""
        assert parse_place_query("Красное Липецкая область").region_key == "липецкая"

    def test_settlement_word_survives_when_it_is_the_name(self) -> None:
        """«Село» — настоящее название деревни в Карелии, выбрасывать нечего."""
        assert parse_place_query("Село").name == "село"
