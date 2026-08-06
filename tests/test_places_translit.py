"""Транслитерация: на ней держится поиск деревень без русского имени.

У четверти мест СНГ в источнике только латинское написание. Если эти
преобразования разъедутся с романизацией GeoNames, человек из такой деревни
снова упрётся в «ничего не нашла» — ровно в тот тупик, из-за которого всё
и переделывалось.
"""

from __future__ import annotations

import pytest

from astra.places.translit import fold, has_cyrillic, latin_key, to_cyrillic, to_latin


class TestToLatin:
    """Совпадение с колонкой asciiname GeoNames — не украшение, а контракт."""

    @pytest.mark.parametrize(
        ("russian", "geonames_ascii"),
        [
            ("Жуково", "Zhukovo"),
            ("Зябриково", "Zyabrikovo"),
            ("Знаменка", "Znamenka"),
            ("Житниково", "Zhitnikovo"),
            ("Сокол", "Sokol"),
            ("Череповец", "Cherepovets"),
            ("Чагода", "Chagoda"),
            ("Шексна", "Sheksna"),
            ("Щёлково", "Shchelkovo"),
            ("Южно-Сахалинск", "Yuzhno-Sakhalinsk"),
            ("Ярославль", "Yaroslavl"),
            ("Тимашёвск", "Timashevsk"),
        ],
    )
    def test_matches_geonames_romanization(self, russian: str, geonames_ascii: str) -> None:
        assert to_latin(russian) == fold(geonames_ascii)

    def test_latin_input_passes_through(self) -> None:
        assert to_latin("Sokol") == "sokol"

    def test_diacritics_are_stripped(self) -> None:
        # В источнике попадаются следы чужих раскладок: Sokoł, Ярослáвичи.
        assert to_latin("Ярослáвичи") == to_latin("Ярославичи")
        assert fold("Sokoł") == "sokol"

    def test_yo_reads_as_ye(self) -> None:
        assert to_latin("Тимашёвск") == to_latin("Тимашевск")


class TestToCyrillic:
    """Обратная сторона: человек набирает латиницей."""

    @pytest.mark.parametrize(
        ("latin", "expected"),
        [
            ("Moskva", "москва"),
            ("Zhukovo", "жуково"),
            ("Cherepovets", "череповец"),
            ("Sheksna", "шексна"),
            ("Tashkent", "ташкент"),
        ],
    )
    def test_reads_latin_input(self, latin: str, expected: str) -> None:
        assert to_cyrillic(latin) == expected


class TestLatinKey:
    """Единый ключ: русский запрос и латинская запись должны сойтись."""

    @pytest.mark.parametrize(
        ("query", "stored"),
        [
            ("Зябриково", "Zyabrikovo"),
            ("Жуково", "Zhukovo"),
            ("Знаменка", "Znamenka"),
            ("Ташкент", "Tashkent"),
        ],
    )
    def test_russian_query_matches_latin_record(self, query: str, stored: str) -> None:
        assert latin_key(query) == latin_key(stored)

    def test_wrong_variant_does_not_match(self) -> None:
        # Ровно эта разница отличает «Сокол» от белорусского «Сокал»
        # и не даёт импортёру взять неверное написание.
        assert latin_key("Сокол") == latin_key("Sokol")
        assert latin_key("Сокал") != latin_key("Sokol")


def test_has_cyrillic() -> None:
    assert has_cyrillic("Москва")
    assert not has_cyrillic("Moskva")
    assert has_cyrillic("Ufа")  # смесь алфавитов из живой базы
