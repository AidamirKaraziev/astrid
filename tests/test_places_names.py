"""Откуда у места берётся название.

Каждый случай здесь — из живой базы до переделки. Тесты пришпиливают ровно
те ошибки, из-за которых люди не могли пройти онбординг: Санкт-Петербург
лежал как «Бетъырбух», Владикавказ как «Буро-ГӀала», Череповец как
«Чарапавец» и не находился вовсе.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from astra.places.names import (
    closest_cyrillic_alternate,
    cyrillic_alternates,
    load_official_names,
    resolve_place_name,
)

# Строки один в один из alternateNamesV2.txt: id, geoname_id, язык, название,
# предпочтительное, краткое, разговорное, историческое, с, по.
SPB_LINES = """\
2181407\t498817\tru\tЛенинград\t\t\t\t1\t1924\t1991
2417766\t498817\tru\tСанкт-Петербург\t1\t1\t\t\t\t
2417769\t498817\tru\tПетербург\t\t1\t\t\t\t
2426910\t498817\tru\tПитер\t\t\t1\t\t\t
2432652\t498817\tru\tПетроград\t\t\t\t1\t1914\t1924
6054463\t569223\tru\tЧереповец\t1\t\t\t\t\t
3130190\t462300\t\tЗнаменка\t\t\t\t\t\t
5953549\t462300\tru\tЗнаменка\t\t\t\t\t\t
9900001\t111111\ten\tSomewhere\t1\t\t\t\t\t
"""


@pytest.fixture
def alternate_names_file(tmp_path: Path) -> Path:
    path = tmp_path / "alternateNamesV2.txt"
    path.write_text(SPB_LINES, encoding="utf-8")
    return path


class TestLoadOfficialNames:
    def test_prefers_the_preferred_name(self, alternate_names_file: Path) -> None:
        names = load_official_names(alternate_names_file)
        assert names[498817] == "Санкт-Петербург"

    def test_historic_names_never_win(self, alternate_names_file: Path) -> None:
        """Ленинград и Петроград помечены историческими — они не имя города."""
        names = load_official_names(alternate_names_file)
        assert names[498817] not in {"Ленинград", "Петроград"}

    def test_colloquial_names_never_win(self, alternate_names_file: Path) -> None:
        names = load_official_names(alternate_names_file)
        assert names[498817] != "Питер"

    def test_plain_name_used_when_nothing_is_preferred(
        self,
        alternate_names_file: Path,
    ) -> None:
        names = load_official_names(alternate_names_file)
        assert names[462300] == "Знаменка"

    def test_other_languages_ignored(self, alternate_names_file: Path) -> None:
        names = load_official_names(alternate_names_file)
        assert 111111 not in names

    def test_needed_filter_narrows_the_dictionary(self, alternate_names_file: Path) -> None:
        names = load_official_names(alternate_names_file, needed={569223})
        assert names == {569223: "Череповец"}


class TestClosestAlternate:
    """Ступень, отличающая «Сокол» от белорусского «Сокал»."""

    def test_picks_the_variant_matching_latin_spelling(self) -> None:
        alternates = ["Sokal", "Sokol", "Sokoł", "Сокал", "Сокол"]
        assert closest_cyrillic_alternate(alternates, "Sokol") == "Сокол"

    def test_picks_russian_over_ukrainian(self) -> None:
        assert closest_cyrillic_alternate(["Іжевськ", "Ижевск"], "Izhevsk") == "Ижевск"

    def test_returns_none_without_cyrillic(self) -> None:
        assert closest_cyrillic_alternate(["Zyabrikovo"], "Zyabrikovo") is None


class TestResolvePlaceName:
    def test_official_name_wins_over_junk_alternates(self) -> None:
        """Тот самый случай: в синонимах чего только нет, но имя — из источника."""
        resolved = resolve_place_name(
            ascii_name="Saint Petersburg",
            alternates=["Leningrad", "Бетъырбух", "Ленинград", "Питер"],
            official_name="Санкт-Петербург",
        )
        assert resolved.name == "Санкт-Петербург"
        assert resolved.is_latin is False

    def test_vladikavkaz_is_not_a_chechen_name(self) -> None:
        resolved = resolve_place_name(
            ascii_name="Vladikavkaz",
            alternates=["Буро-ГӀала", "Дзауджикау", "Владикавказ"],
            official_name="Владикавказ",
        )
        assert resolved.name == "Владикавказ"

    def test_falls_back_to_closest_alternate(self) -> None:
        resolved = resolve_place_name(
            ascii_name="Sokol",
            alternates=["Sokal", "Sokol", "Сокал", "Сокол"],
            official_name=None,
        )
        assert resolved.name == "Сокол"
        assert resolved.is_latin is False

    def test_cyrillic_in_main_field_is_taken_as_is(self) -> None:
        resolved = resolve_place_name(
            ascii_name="Центральный Район",
            alternates=[],
            official_name=None,
        )
        assert resolved.name == "Центральный Район"
        assert resolved.is_latin is False

    def test_latin_stays_latin_when_nothing_russian_exists(self) -> None:
        """Придумывать написание нельзя: транслитерация врёт, а это место рождения."""
        resolved = resolve_place_name(
            ascii_name="Zyabrikovo",
            alternates=["Zyabrikovo"],
            official_name=None,
        )
        assert resolved.name == "Zyabrikovo"
        assert resolved.is_latin is True

    def test_alternates_are_kept_for_search(self) -> None:
        resolved = resolve_place_name(
            ascii_name="Nizhny Novgorod",
            alternates=["Горький", "Нижний Новгород"],
            official_name="Нижний Новгород",
        )
        # Историческое имя основным не станет, но искать по нему можно:
        # человек может помнить город как Горький.
        assert "Горький" in resolved.alternates
        assert "Нижний Новгород" in resolved.alternates

    def test_alternates_differing_only_in_soft_sign_are_deduplicated(self) -> None:
        """«Казань» и «Казан» ищутся одинаково — второй в индексе не нужен."""
        resolved = resolve_place_name(
            ascii_name="Kazan",
            alternates=["Kazan", "Казань", "Казан"],
            official_name="Казань",
        )
        assert resolved.alternates == ("Казань",)


def test_cyrillic_alternates_drop_duplicates_and_latin() -> None:
    assert cyrillic_alternates(["Moskva", "Москва", "Москвa", "  Москва  "]) == ["Москва"]
