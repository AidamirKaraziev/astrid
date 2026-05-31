from astra.places.geonames_import import parse_ru_line


def test_parse_ru_line_moscow() -> None:
    line = (
        "524901\tMoscow\tMoscow\t4953482\t55.75222\t37.61556\tP\tPPLC\tRU\t\t"
        "48\t524894\t524901\t\t13181509\t\t\tEurope/Moscow\t2025-09-05\n"
    )
    row = parse_ru_line(line, admin1_names={"48": "Moscow Oblast"})
    assert row is not None
    assert row["geoname_id"] == 524901
    assert row["country_code"] == "RU"
    assert row["feature_code"] == "PPLC"
    assert row["timezone"] == "Europe/Moscow"
    assert row["name_normalized"]


def test_parse_ru_line_skips_non_populated_place() -> None:
    line = (
        "2017370\tRussian Federation\tRussian Federation\t\t60\t100\t"
        "A\tPCLI\tRU\t\t\t\t\t\t\t\t\t\n"
    )
    assert parse_ru_line(line, admin1_names={}) is None


def test_parse_ru_line_skips_non_ru() -> None:
    line = (
        "2988507\tParis\tParis\t\t48.85341\t2.3488\tP\tPPLC\tFR\t\t"
        "11\t\t\t\t2161000\t\tEurope/Paris\t\n"
    )
    assert parse_ru_line(line, admin1_names={}) is None
