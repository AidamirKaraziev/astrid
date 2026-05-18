from astra.places.normalize import build_display_name, normalize_place_query


def test_normalize_yo() -> None:
    assert normalize_place_query("  Ёлочка  ") == "елочка"


def test_build_display_name() -> None:
    assert build_display_name("Казань", "Tatarstan") == "Казань, Tatarstan, Россия"
    assert build_display_name("Вырица", None) == "Вырица, Россия"
