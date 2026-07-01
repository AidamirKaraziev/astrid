"""Регистрация TTF с кириллицей для ReportLab."""

from __future__ import annotations

from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from astra.reports.synastry.theme import FONT, FONT_BOLD

_FONTS_REGISTERED = False

_FONT_REGULAR = "CormorantGaramond-Regular.ttf"
_FONT_BOLD = "CormorantGaramond-Bold.ttf"


def bundled_fonts_dir() -> Path:
    return Path(__file__).resolve().parent / "assets" / "fonts"


def register_synastry_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    bundled = bundled_fonts_dir()
    regular = bundled / _FONT_REGULAR
    bold = bundled / _FONT_BOLD
    if not regular.is_file() or not bold.is_file():
        msg = (
            f"Не найден TTF с кириллицей. "
            f"Ожидаются {_FONT_REGULAR} и {_FONT_BOLD} в {bundled}/."
        )
        raise RuntimeError(msg)

    pdfmetrics.registerFont(TTFont(FONT, str(regular)))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold)))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD)
    _FONTS_REGISTERED = True
