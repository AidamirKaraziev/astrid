"""Регистрация шрифтов PDF натала: PT Sans (текст) + DejaVuSans (астро-глифы)."""

from __future__ import annotations

from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from astra.reports.natal.glyphs import ALL_GLYPH_CHARS, FONT_GLYPHS
from astra.reports.synastry.fonts import register_synastry_fonts

_FONTS_REGISTERED = False

_GLYPH_FONT_FILE = "DejaVuSans.ttf"


def bundled_fonts_dir() -> Path:
    return Path(__file__).resolve().parent / "assets" / "fonts"


def verify_glyph_coverage(font: TTFont) -> list[str]:
    """Символы из ALL_GLYPH_CHARS, отсутствующие в cmap шрифта."""
    cmap = font.face.charToGlyph
    return [ch for ch in ALL_GLYPH_CHARS if ord(ch) not in cmap]


def register_natal_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    register_synastry_fonts()

    glyph_path = bundled_fonts_dir() / _GLYPH_FONT_FILE
    if not glyph_path.is_file():
        msg = f"Не найден шрифт астро-глифов: {glyph_path}"
        raise RuntimeError(msg)

    font = TTFont(FONT_GLYPHS, str(glyph_path))
    missing = verify_glyph_coverage(font)
    if missing:
        msg = f"{_GLYPH_FONT_FILE} не покрывает глифы: {missing}"
        raise RuntimeError(msg)

    pdfmetrics.registerFont(font)
    _FONTS_REGISTERED = True
