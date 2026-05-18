from astra.places.normalize import (
    build_search_text,
    extract_cyrillic_alternates,
    resolve_russian_place_name,
)


def test_resolve_moscow_from_alternates() -> None:
    name_ru, alts = resolve_russian_place_name(
        "Moscow",
        "Moscow,Москва,Moskva,Mockba",
    )
    assert name_ru == "Москва"
    assert "Москва" in alts


def test_search_text_includes_ascii_and_cyrillic() -> None:
    text = build_search_text(
        name_ru="Казань",
        name_ascii="Kazan",
        cyrillic_alternates=["Казань"],
        admin1_ru="Республика Татарстан",
    )
    assert "казань" in text
    assert "kazan" in text
    assert "татарстан" in text


def test_extract_cyrillic_skips_latin() -> None:
    assert extract_cyrillic_alternates("Kazan,Москва,MSK") == ["Москва"]
