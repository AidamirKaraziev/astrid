"""Нормализация названий для поиска (ё→е, регистр, кириллица)."""

_YO_MAP = str.maketrans({"ё": "е", "Ё": "Е"})


def has_cyrillic(text: str) -> bool:
    return any("\u0400" <= char <= "\u04FF" for char in text)


def normalize_place_query(text: str) -> str:
    return " ".join(text.strip().translate(_YO_MAP).lower().split())


def extract_cyrillic_alternates(alternatenames: str) -> list[str]:
    """Русские (кириллические) варианты из поля alternatenames GeoNames."""
    result: list[str] = []
    seen: set[str] = set()
    for raw in alternatenames.split(","):
        name = raw.strip()
        if len(name) < 2 or not has_cyrillic(name):
            continue
        key = normalize_place_query(name)
        if key in seen:
            continue
        seen.add(key)
        result.append(name)
    return result


def resolve_russian_place_name(ascii_name: str, alternatenames: str) -> tuple[str, list[str]]:
    """
    GeoNames хранит name в ASCII; русское название — в alternatenames.
    Возвращает (основное_имя_для_UI, все_кириллические_синонимы).
    """
    cyrillic_names = extract_cyrillic_alternates(alternatenames)
    if has_cyrillic(ascii_name):
        primary = ascii_name.strip()
    elif cyrillic_names:
        primary = cyrillic_names[0]
    else:
        primary = ascii_name.strip()
    return primary, cyrillic_names


def build_display_name(name: str, admin1_name: str | None) -> str:
    if admin1_name and normalize_place_query(admin1_name) != normalize_place_query(name):
        return f"{name}, {admin1_name}, Россия"
    return f"{name}, Россия"


def build_search_text(
    *,
    name_ru: str,
    name_ascii: str,
    cyrillic_alternates: list[str],
    admin1_ru: str | None,
) -> str:
    """Индекс для поиска: кириллица + латиница (на случай ввода Moskva/Moscow)."""
    parts = [name_ru, name_ascii, *cyrillic_alternates]
    if admin1_ru:
        parts.append(admin1_ru)
    return normalize_place_query(" ".join(parts))
