"""Разбор дампа GeoNames: что попадает в справочник, а что нет.

Состав справочника — не вкусовщина, а продуктовое решение. Хутора и
упразднённые сёла нужны: это чьи-то места рождения. Фермы, урочища и
микрорайоны — нет: из семнадцати тысяч таких записей собственное имя есть
у восьмисот, остальное «Отделение Совхоза Номер Три», а списки тёзок они
засоряют. Микрорайоны — прямая причина, по которой на «Санкт-Петербург» бот
отвечал «Калининский, Красногвардейский, Центральный».
"""

from __future__ import annotations

import pytest

from astra.places.geonames_import import build_search_blob, parse_dump_line

MOSCOW = (
    "524901\tMoscow\tMoscow\tMoskva,Москва\t55.75222\t37.61556\tP\tPPLC\tRU\t\t"
    "48\t524894\t524901\t\t13181509\t\t\tEurope/Moscow\t2025-09-05\n"
)
ALMATY = (
    "1526384\tAlmaty\tAlmaty\tAlma-Ata,Алматы,Алма-Ата\t43.25667\t76.92861\tP\tPPLA\tKZ\t\t"
    "01\t\t\t\t1977011\t\t\tAsia/Almaty\t2025-01-01\n"
)


class TestParseDumpLine:
    def test_reads_a_city(self) -> None:
        place = parse_dump_line(MOSCOW)
        assert place is not None
        assert place.geoname_id == 524901
        assert place.country_code == "RU"
        assert place.feature_code == "PPLC"
        assert place.timezone == "Europe/Moscow"
        assert place.population == 13181509
        assert "Москва" in place.alternates

    def test_reads_a_city_outside_russia(self) -> None:
        """Ровно то, чего не было: до переделки всё, кроме РФ, выбрасывалось."""
        place = parse_dump_line(ALMATY)
        assert place is not None
        assert place.country_code == "KZ"
        assert place.timezone == "Asia/Almaty"

    @pytest.mark.parametrize(
        ("feature_class", "feature_code"),
        [
            ("A", "PCLI"),  # страна целиком
            ("P", "PPLX"),  # микрорайон: «Калининский, Санкт-Петербург»
            ("S", "FRM"),  # «Отделение Совхоза Номер Три»
            ("L", "AREA"),  # «Урочище Раменский Мох»
            ("H", "STM"),  # река
        ],
    )
    def test_skips_what_is_not_a_settlement(
        self,
        feature_class: str,
        feature_code: str,
    ) -> None:
        line = (
            f"1\tSomething\tSomething\t\t55.0\t37.0\t{feature_class}\t{feature_code}\tRU\t\t"
            "48\t\t\t\t0\t\t\tEurope/Moscow\t\n"
        )
        assert parse_dump_line(line) is None

    @pytest.mark.parametrize("feature_code", ["PPL", "PPLQ", "PPLH", "PPLA2", "PPLF"])
    def test_keeps_settlements_including_abandoned(self, feature_code: str) -> None:
        """Расселённая в девяностых деревня — тоже чьё-то место рождения."""
        line = (
            f"1\tDerevnya\tDerevnya\tДеревня\t55.0\t37.0\tP\t{feature_code}\tRU\t\t"
            "48\t\t\t\t0\t\t\tEurope/Moscow\t\n"
        )
        assert parse_dump_line(line) is not None

    def test_skips_country_outside_the_fifteen(self) -> None:
        line = (
            "2988507\tParis\tParis\t\t48.85341\t2.3488\tP\tPPLC\tFR\t\t"
            "11\t\t\t\t2161000\t\tEurope/Paris\t\n"
        )
        assert parse_dump_line(line) is None

    def test_skips_broken_line(self) -> None:
        assert parse_dump_line("мусор\n") is None

    def test_skips_line_with_unparsable_coordinates(self) -> None:
        line = (
            "1\tX\tX\t\tсевернее\tвосточнее\tP\tPPL\tRU\t\t"
            "48\t\t\t\t0\t\t\tEurope/Moscow\t\n"
        )
        assert parse_dump_line(line) is None


class TestSearchBlob:
    def test_contains_every_way_to_ask(self) -> None:
        blob = build_search_blob(
            name="Алматы",
            ascii_name="Almaty",
            alternates=("Алматы", "Алма-Ата"),
            region="Алматы",
            country="Казахстан",
        )
        for fragment in ("алматы", "almaty", "алма-ата", "казахстан"):
            assert fragment in blob

    def test_is_normalized(self) -> None:
        blob = build_search_blob(
            name="Тимашёвск",
            ascii_name="Timashevsk",
            alternates=(),
            region=None,
            country="Россия",
        )
        assert "тимашевск" in blob  # ё свернулась в е
        assert blob == blob.lower()
