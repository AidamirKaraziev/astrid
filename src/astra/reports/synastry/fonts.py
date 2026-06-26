"""Регистрация TTF с кириллицей для ReportLab."""

from __future__ import annotations

from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from astra.reports.synastry.theme import FONT, FONT_BOLD

_FONTS_REGISTERED = False


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def register_synastry_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    root = repo_root()
    candidates: list[tuple[Path, Path]] = [
        (root / "data/fonts/DejaVuSans.ttf", root / "data/fonts/DejaVuSans-Bold.ttf"),
        (
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
    ]
    for regular, bold in candidates:
        if regular.is_file() and bold.is_file():
            pdfmetrics.registerFont(TTFont(FONT, str(regular)))
            pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold)))
            pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD)
            _FONTS_REGISTERED = True
            return
    msg = "Не найден TTF с кириллицей. Положи DejaVuSans в data/fonts/."
    raise RuntimeError(msg)
