"""Пол пользователя для промптов и синастрии."""

from __future__ import annotations

from typing import Literal

Gender = Literal["мужчина", "женщина"]

GENDER_MALE: Gender = "мужчина"
GENDER_FEMALE: Gender = "женщина"

GENDER_VALUES: frozenset[str] = frozenset({GENDER_MALE, GENDER_FEMALE})


def gender_display_label(gender: Gender | None) -> str | None:
    """Подпись для UI: None если пол не задан."""
    if gender == GENDER_MALE:
        return "👨 Мужчина"
    if gender == GENDER_FEMALE:
        return "👩 Женщина"
    return None


def normalize_gender(value: str | None) -> Gender | None:
    """Привести ввод к допустимому значению или None."""
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in GENDER_VALUES:
        return normalized  # type: ignore[return-value]
    return None
