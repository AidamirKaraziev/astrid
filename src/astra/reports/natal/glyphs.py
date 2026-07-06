"""Астрологические глифы для колеса карты и таблиц.

PT Sans не содержит астро-символов (рендерит .notdef), поэтому глифы
рисуются шрифтом AstroGlyphs (DejaVuSans, свободная лицензия).
Покрытие проверяется при регистрации шрифта — см. fonts.verify_glyph_coverage.
"""

from __future__ import annotations

FONT_GLYPHS = "AstroGlyphs"

# en-ключ точки (как в FullNatalChart) → глиф
POINT_GLYPH: dict[str, str] = {
    "Sun": "☉",
    "Moon": "☽",
    "Mercury": "☿",
    "Venus": "♀",
    "Mars": "♂",
    "Jupiter": "♃",
    "Saturn": "♄",
    "Uranus": "♅",
    "Neptune": "♆",
    "Pluto": "♇",
    "Chiron": "⚷",
    "Mean_Lilith": "⚸",
    "True_North_Lunar_Node": "☊",
    "True_South_Lunar_Node": "☋",
}

# порядок знаков от 0° Овна; глифы для зодиакального кольца
SIGN_GLYPHS: tuple[str, ...] = ("♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓")

ASPECT_GLYPH: dict[str, str] = {
    "соединение": "☌",
    "оппозиция": "☍",
    "трин": "△",
    "квадрат": "□",
    "секстиль": "✶",
}

ALL_GLYPH_CHARS: tuple[str, ...] = tuple(
    sorted(set(POINT_GLYPH.values()) | set(SIGN_GLYPHS) | set(ASPECT_GLYPH.values()))
)
