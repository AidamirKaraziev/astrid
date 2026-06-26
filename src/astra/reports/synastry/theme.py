"""Константы вёрстки и визуальной темы PDF синастрии."""

from __future__ import annotations

from reportlab.lib import colors

# --- размеры страницы (mobile portrait) ---
W, H = 390, 844
MARGIN = 16
CONTENT_W = W - 2 * MARGIN
FOOTER_TOP = 34
CONTENT_BOTTOM = FOOTER_TOP + 8

FONT = "AstraSans"
FONT_BOLD = "AstraSans-Bold"

GAP = {"xs": 6, "sm": 10, "md": 14, "lg": 18}
TYPE = {"caption": 11, "body": 14, "h2": 17, "h1": 20, "display": 26, "quote": 15}
LEADING = {"body": 19, "caption": 15}

# --- палитра ---
BG_DARK = colors.HexColor("#0D0D1A")
BG_CARD = colors.HexColor("#1A1A2E")
BG_CARD_DEEP = colors.HexColor("#12121F")
GOLD = colors.HexColor("#C9A96E")
GOLD_LIGHT = colors.HexColor("#E8C98A")
GOLD_DIM = colors.HexColor("#8A7348")
CREAM = colors.HexColor("#E8E4DC")
MUTED = colors.HexColor("#9A9AB0")
ACCENT_BLUE = colors.HexColor("#5B7FD4")
ACCENT_PURPLE = colors.HexColor("#8B5CF6")
TRINE_COLOR = colors.HexColor("#4CAF89")
SQUARE_COLOR = colors.HexColor("#E07B4F")
CONJ_COLOR = colors.HexColor("#5B7FD4")
SEXT_COLOR = colors.HexColor("#9B7FD4")
OPPO_COLOR = colors.HexColor("#E05050")
NEBULA_BLUE = colors.HexColor("#4A5FA0")
NEBULA_PURPLE = colors.HexColor("#5A4588")
STAR_CREAM = colors.HexColor("#EEE9DC")
STAR_GOLD = colors.HexColor("#F0D9A0")
STAR_BLUE = colors.HexColor("#B8C8F0")
STAR_LILAC = colors.HexColor("#CDB8F5")

GLOW_STRENGTH = {
    "finale": (1.0, 2.0),
    "section": (0.78, 0.78),
    "card": (0.55, 0.68),
}
FINALE_RING_MUL = 2.0

CTA_BUTTON_H = 48

_STAR_COLORS = {
    "cream": STAR_CREAM,
    "gold": STAR_GOLD,
    "blue": STAR_BLUE,
    "lilac": STAR_LILAC,
}

_COSMIC_STARS: list[tuple[str, float, float, float, float, str]] = [
    ("dot", 24, 818, 1.0, 0.45, "cream"),
    ("sparkle", 72, 792, 3.2, 0.72, "gold"),
    ("dot", 128, 826, 0.9, 0.38, "blue"),
    ("plus", 186, 778, 2.8, 0.55, "cream"),
    ("dot", 248, 814, 1.1, 0.42, "lilac"),
    ("sparkle", 312, 786, 2.6, 0.65, "gold"),
    ("dot", 358, 822, 0.8, 0.35, "cream"),
    ("diamond", 340, 748, 2.2, 0.5, "blue"),
    ("dot", 44, 702, 1.2, 0.4, "cream"),
    ("sparkle", 118, 668, 2.4, 0.58, "lilac"),
    ("dot", 210, 718, 0.9, 0.36, "gold"),
    ("plus", 286, 690, 2.4, 0.48, "cream"),
    ("dot", 366, 712, 1.0, 0.4, "blue"),
    ("sparkle", 30, 598, 2.8, 0.6, "gold"),
    ("dot", 98, 562, 1.1, 0.42, "cream"),
    ("diamond", 164, 612, 1.8, 0.45, "lilac"),
    ("dot", 238, 578, 0.9, 0.38, "blue"),
    ("plus", 318, 604, 2.2, 0.52, "gold"),
    ("sparkle", 372, 548, 2.0, 0.55, "cream"),
    ("dot", 52, 468, 1.0, 0.4, "lilac"),
    ("sparkle", 142, 442, 3.0, 0.62, "gold"),
    ("dot", 228, 486, 0.8, 0.35, "cream"),
    ("plus", 302, 452, 2.6, 0.5, "blue"),
    ("dot", 356, 418, 1.1, 0.42, "gold"),
    ("sparkle", 38, 358, 2.2, 0.58, "cream"),
    ("dot", 108, 322, 1.0, 0.4, "blue"),
    ("diamond", 178, 368, 2.0, 0.48, "gold"),
    ("dot", 262, 338, 0.9, 0.36, "lilac"),
    ("sparkle", 328, 362, 2.8, 0.64, "gold"),
    ("plus", 368, 298, 2.0, 0.46, "cream"),
    ("dot", 22, 228, 1.1, 0.42, "gold"),
    ("sparkle", 88, 198, 3.4, 0.7, "gold"),
    ("dot", 156, 248, 0.9, 0.38, "cream"),
    ("plus", 224, 212, 2.4, 0.5, "lilac"),
    ("dot", 298, 178, 1.0, 0.4, "blue"),
    ("sparkle", 352, 218, 2.4, 0.6, "cream"),
    ("dot", 48, 128, 1.0, 0.4, "blue"),
    ("diamond", 132, 98, 2.4, 0.55, "gold"),
    ("dot", 208, 142, 0.9, 0.36, "cream"),
    ("sparkle", 278, 108, 3.0, 0.68, "gold"),
    ("plus", 342, 138, 2.2, 0.48, "lilac"),
    ("dot", 18, 58, 1.1, 0.42, "cream"),
    ("sparkle", 98, 42, 2.6, 0.6, "gold"),
    ("dot", 188, 68, 0.8, 0.35, "blue"),
    ("sparkle", 268, 52, 2.2, 0.55, "lilac"),
    ("dot", 348, 78, 1.0, 0.4, "cream"),
]

_FINALE_EXTRA_STARS: list[tuple[str, float, float, float, float, str]] = [
    ("sparkle", 60, 520, 4.2, 0.85, "gold"),
    ("sparkle", 330, 480, 3.8, 0.8, "gold"),
    ("plus", 195, 620, 3.2, 0.7, "gold"),
    ("diamond", 280, 720, 2.8, 0.65, "lilac"),
    ("sparkle", 120, 380, 3.6, 0.75, "gold"),
    ("plus", 300, 320, 2.8, 0.62, "cream"),
]

ASPECT_STYLES: dict[str, tuple[colors.Color, str, str]] = {
    "соединение": (CONJ_COLOR, "☌", "Соединение"),
    "трин": (TRINE_COLOR, "△", "Трин"),
    "квадрат": (SQUARE_COLOR, "□", "Квадрат"),
    "секстиль": (SEXT_COLOR, "✶", "Секстиль"),
    "оппозиция": (OPPO_COLOR, "☍", "Оппозиция"),
}

PLANET_LABELS = {
    "sun": "☉ Солнце",
    "moon": "☽ Луна",
    "asc": "↑ Асцендент",
    "mercury": "☿ Меркурий",
    "venus": "♀ Венера",
    "mars": "♂ Марс",
    "jupiter": "♃ Юпитер",
    "saturn": "♄ Сатурн",
}

LEGEND_ITEMS = [
    (CONJ_COLOR, "☌ Соединение", "слияние"),
    (TRINE_COLOR, "△ Трин", "поток"),
    (SEXT_COLOR, "✶ Секстиль", "возможность"),
    (SQUARE_COLOR, "□ Квадрат", "рост"),
    (OPPO_COLOR, "☍ Оппозиция", "баланс"),
]


def person_initials(name: str) -> str:
    """Первые две буквы имени для аватарки на обложке."""
    return name[:2].upper()


def star_color(color_key: str) -> colors.Color:
    return _STAR_COLORS[color_key]


def iter_cosmic_stars(*, rich: bool = False) -> list[tuple[str, float, float, float, float, str]]:
    stars = list(_COSMIC_STARS)
    if rich:
        stars.extend(_FINALE_EXTRA_STARS)
    return stars
