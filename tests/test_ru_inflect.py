from astra.text.ru_inflect import format_name_cases, inflect_name


def test_inflect_name_dative() -> None:
    assert inflect_name("Аида", "datv") == "Аиде"
    assert inflect_name("Анна", "datv") == "Анне"


def test_format_name_cases_includes_all_cases() -> None:
    cases = format_name_cases("Мария")
    assert "именительный: Мария" in cases
    assert "дательный: Марии" in cases
