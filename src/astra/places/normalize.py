"""Нормализация названий для поиска (ё→е, регистр, кириллица).

Разбор синонимов из дампа переехал в `astra.places.names`: там у названий
есть языковые метки, и «первый попавшийся кириллический вариант» больше не
может стать именем города.
"""

_YO_MAP = str.maketrans({"ё": "е", "Ё": "Е"})


def has_cyrillic(text: str) -> bool:
    return any("\u0400" <= char <= "\u04FF" for char in text)


def normalize_place_query(text: str) -> str:
    return " ".join(text.strip().translate(_YO_MAP).lower().split())


def build_display_name(
    name: str,
    admin1_name: str | None,
    country_name: str = "Россия",
) -> str:
    """«Вырица, Ленинградская область, Россия».

    Регион опускается, когда повторяет название места: «Москва, Москва,
    Россия» человек читает как ошибку.
    """
    if admin1_name and normalize_place_query(admin1_name) != normalize_place_query(name):
        return f"{name}, {admin1_name}, {country_name}"
    return f"{name}, {country_name}"
