#!/usr/bin/env python3
"""Превью: классическая карточка + индикатор (3 варианта позиции шкалы)."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors

from astra.reports.synastry import build_prototype_report, register_synastry_fonts
from astra.reports.synastry.builder import SynastryPdfBuilder
from astra.reports.synastry.theme import (
    BG_DARK,
    CONTENT_W,
    CREAM,
    FONT,
    FONT_BOLD,
    GOLD,
    GOLD_DIM,
    GOLD_LIGHT,
    H,
    MARGIN,
    MUTED,
    TYPE,
    W,
    person_initials,
)

_TRACK = colors.HexColor("#252538")

# bar_y — от низа карточки; чем меньше значение, тем ниже шкала
_VARIANT_META: dict[str, tuple[str, str, float, str]] = {
    "G": ("Простор", "шкала в нижней трети, 79% над линией, отступ от имён 48px", 108.0, "above"),
    "H": ("Подвал", "шкала у дна карточки, % на бегунке, даты выше", 78.0, "knob"),
    "I": ("Ярус", "79% в кольце, шкала отдельным ярусом над датами", 100.0, "ring"),
}

_Z_VARIANT = 96
_Z_VARIANT_DESC = 82

# Минимальные зазоры (pt)
_GAP_NAMES_TO_METER = 48.0
_GAP_METER_TO_BIRTH = 28.0
_GAP_BIRTH_TO_READ = 20.0


def overall_compatibility_pct(report) -> float:  # noqa: ANN001
    if not report.metrics:
        return 0.0
    return sum(m.value for m in report.metrics) / len(report.metrics)


def format_birth_line(subtitle: str) -> str:
    parts = [p.strip() for p in subtitle.split("·")]
    if len(parts) >= 3:
        return f"{parts[0]} · {parts[1]} · {parts[2]}"
    if len(parts) == 2:
        return f"{parts[0]} · {parts[1]}"
    return subtitle


class CoverCompatPreviewBuilder(SynastryPdfBuilder):
    variant: str = "G"
    compat: float = 0.0

    def build_variants(self, variants: tuple[str, ...] = ("G", "H", "I")) -> None:
        self.total_pages = len(variants)
        for idx, variant in enumerate(variants):
            self.variant = variant
            if idx > 0:
                self.c.showPage()
            self._page_cover_with_compat()
        self.c.save()

    def _page_cover_with_compat(self) -> None:
        self.page_num += 1
        self.c.bookmarkPage(f"cover-{self.variant}")
        if self.page_num == 1:
            self.c.addOutlineEntry("Обложка + индикатор", f"cover-{self.variant}", 0)
        title, _, _, _ = _VARIANT_META.get(self.variant, (self.variant, "", 100.0, "above"))
        self.c.addOutlineEntry(f"Вариант {self.variant} — {title}", f"cover-{self.variant}", 1)

        self._draw_bg(vibe="cover")
        bottom, cy = self._draw_classic_card_shell()
        self._draw_classic_pair_rings(cy)
        bar_y = self._draw_pct_and_meter(bottom, cy)
        self._draw_classic_birth_lines(bar_y, bottom)
        self._draw_classic_read_time(bottom, bar_y)
        self._draw_cover_footer_meta()
        self._draw_footer()

    # --- карточка ---

    def _draw_classic_card_shell(self) -> tuple[float, float]:
        block_h = 448.0
        top = H - MARGIN - 48
        bottom = top - block_h
        self._draw_radial_glow(W / 2, H * 0.46, 150, GOLD, intensity="section")
        self._draw_card_bg(bottom, block_h, accent=GOLD, glow="section")
        # Кольцо выше — оставляем место для индикатора внизу
        cy = bottom + block_h * 0.60
        return bottom, cy

    def _draw_classic_pair_rings(self, cy: float) -> None:
        self.c.saveState()
        self.c.setStrokeColor(GOLD_LIGHT)
        self.c.setStrokeAlpha(0.5)
        self.c.setLineWidth(0.5)
        self.c.circle(W / 2, cy, 88, fill=0, stroke=1)
        self.c.restoreState()
        self.c.setStrokeColor(GOLD_DIM)
        self.c.setLineWidth(0.3)
        self.c.circle(W / 2, cy, 96, fill=0, stroke=1)

        self.c.setFillColor(GOLD_LIGHT)
        self.c.setFont(FONT_BOLD, TYPE["display"])
        self.c.drawCentredString(W / 2, cy + 108, "Синастрия")
        self.c.setFillColor(MUTED)
        self.c.setFont(FONT, TYPE["body"])
        self.c.drawCentredString(W / 2, cy + 86, "Совместимость пары")

        avatar_y = cy + 8
        for dx, person in [(-48, self._report.person_a), (48, self._report.person_b)]:
            cx = W / 2 + dx
            accent = person.accent
            self._draw_radial_glow(cx, avatar_y, 38, accent, intensity="card")
            self.c.setFillColor(BG_DARK)
            self.c.setStrokeColor(accent)
            self.c.setLineWidth(1.2)
            self.c.circle(cx, avatar_y, 28, fill=1, stroke=1)
            self.c.setFillColor(accent)
            self.c.setFont(FONT_BOLD, 12)
            self.c.drawCentredString(cx, avatar_y - 4, person_initials(person.name))
            self.c.setFillColor(CREAM)
            self.c.setFont(FONT, TYPE["caption"])
            self.c.drawCentredString(cx, avatar_y - 40, person.name)

        pct_mode = _VARIANT_META.get(self.variant, ("", "", 100.0, "above"))[3]
        if pct_mode != "ring":
            self._draw_sparkle(W / 2, avatar_y + 2, 3, GOLD_LIGHT)
            self.c.setFillColor(GOLD)
            self.c.setFont(FONT_BOLD, 14)
            self.c.drawCentredString(W / 2, avatar_y - 2, "×")

    def _names_bottom_y(self, cy: float) -> float:
        return cy + 8 - 40 - 11  # baseline имени − высота строки

    def _draw_zone_divider(self, y: float) -> None:
        """Тонкий разделитель между зоной пары и индикатором."""
        self.c.saveState()
        self.c.setStrokeColor(GOLD_DIM)
        self.c.setStrokeAlpha(0.2)
        self.c.setLineWidth(0.5)
        self.c.line(MARGIN + 24, y, W - MARGIN - 24, y)
        self.c.restoreState()

    def _draw_classic_birth_lines(self, bar_y: float, bottom: float) -> None:
        _, _, _, pct_mode = _VARIANT_META.get(self.variant, ("", "", 100.0, "above"))
        if pct_mode == "knob":
            y_a = bottom + 148
            y_b = y_a - 16
        else:
            y_a = bar_y - _GAP_METER_TO_BIRTH
            y_b = y_a - 16
        self.c.setFont(FONT, TYPE["caption"])
        self.c.setFillColor(MUTED)
        self.c.drawCentredString(W / 2, y_a, format_birth_line(self._report.person_a.subtitle))
        self.c.drawCentredString(W / 2, y_b, format_birth_line(self._report.person_b.subtitle))

    def _draw_classic_read_time(self, bottom: float, bar_y: float) -> None:
        _, _, _, pct_mode = _VARIANT_META.get(self.variant, ("", "", 100.0, "above"))
        if pct_mode == "knob":
            read_y = bottom + 52
        else:
            read_y = bar_y - _GAP_METER_TO_BIRTH - _GAP_BIRTH_TO_READ - 32
        self.c.setFillColor(GOLD)
        self.c.setFont(FONT, TYPE["caption"])
        self.c.drawCentredString(W / 2, read_y, f"✦  {self._report.read_time_label}  ✦")

    def _draw_cover_footer_meta(self) -> None:
        title, subtitle, _, _ = _VARIANT_META.get(self.variant, (self.variant, "", 100.0, "above"))
        self.c.setFillColor(GOLD_DIM)
        self.c.setFont(FONT_BOLD, TYPE["caption"])
        self.c.drawCentredString(W / 2, _Z_VARIANT, f"Вариант {self.variant} — {title}")
        self.c.setFillColor(MUTED)
        self.c.setFont(FONT, 9)
        self.c.drawCentredString(W / 2, _Z_VARIANT_DESC, subtitle)

    # --- индикатор ---

    def _meter_geometry(self, bottom: float) -> tuple[float, float, float, float]:
        _, _, bar_offset, _ = _VARIANT_META.get(self.variant, ("", "", 118.0, "above"))
        bar_w = CONTENT_W - 56
        bar_x = MARGIN + 28
        bar_h = 7.0
        bar_y = bottom + bar_offset
        return bar_x, bar_y, bar_w, bar_h

    def _draw_glowing_bar(self, x: float, y: float, width: float, height: float, pct: float) -> float:
        r = height / 2
        self.c.setFillColor(_TRACK)
        self.c.roundRect(x, y, width, height, r, fill=1, stroke=0)
        fill_w = max(height, width * pct)
        if pct <= 0:
            return x

        end_x = x + fill_w
        mid_y = y + height / 2
        self._draw_radial_glow(end_x, mid_y, height * 4.2, GOLD, intensity="section")
        self._draw_radial_glow(end_x, mid_y, height * 2.0, GOLD_LIGHT, intensity="finale")
        self.c.setFillColor(GOLD)
        self.c.roundRect(x, y, fill_w, height, r, fill=1, stroke=0)
        self.c.setFillColor(GOLD_LIGHT)
        self.c.setFillAlpha(0.48)
        self.c.roundRect(x, y + height * 0.18, fill_w, height * 0.38, height * 0.1, fill=1, stroke=0)
        self.c.setFillAlpha(1)
        self.c.setFillColor(GOLD_LIGHT)
        self.c.circle(end_x, mid_y, height * 0.58, fill=1, stroke=0)
        return end_x

    def _draw_meter_labels(self, bar_x: float, bar_y: float, bar_w: float, bar_h: float) -> None:
        self.c.setFillColor(MUTED)
        self.c.setFont(FONT, 9)
        self.c.drawCentredString(W / 2, bar_y + bar_h + 14, "общая совместимость")
        self.c.setFillColor(GOLD_DIM)
        self.c.setFont(FONT, 8)
        self.c.drawString(bar_x, bar_y - 11, "0")
        self.c.drawRightString(bar_x + bar_w, bar_y - 11, "100")

    def _draw_hero_pct(self, cx: float, cy: float, pct_label: int, *, size: int = 34) -> None:
        num_w = self.c.stringWidth(str(pct_label), FONT_BOLD, size)
        pct_w = self.c.stringWidth("%", FONT_BOLD, 13)
        x0 = cx - (num_w + pct_w + 2) / 2
        self.c.setFillColor(GOLD_LIGHT)
        self.c.setFont(FONT_BOLD, size)
        self.c.drawString(x0, cy, str(pct_label))
        self.c.setFillColor(GOLD)
        self.c.setFont(FONT_BOLD, 13)
        self.c.drawString(x0 + num_w + 2, cy + size * 0.28, "%")

    def _draw_pct_and_meter(self, bottom: float, cy: float) -> float:
        pct_label = int(round(self.compat * 100))
        _, _, _, pct_mode = _VARIANT_META.get(self.variant, ("", "", 118.0, "above"))
        bar_x, bar_y, bar_w, bar_h = self._meter_geometry(bottom)

        # Разделитель между парой и индикатором
        names_bottom = self._names_bottom_y(cy)
        divider_y = names_bottom - 20
        self._draw_zone_divider(divider_y)

        if pct_mode == "above":
            self._draw_hero_pct(W / 2, bar_y + 40, pct_label, size=34)
            self._draw_meter_labels(bar_x, bar_y, bar_w, bar_h)
            self._draw_glowing_bar(bar_x, bar_y, bar_w, bar_h, self.compat)

        elif pct_mode == "knob":
            self._draw_meter_labels(bar_x, bar_y, bar_w, bar_h)
            end_x = self._draw_glowing_bar(bar_x, bar_y, bar_w, bar_h, self.compat)
            self._draw_hero_pct(end_x, bar_y + bar_h + 26, pct_label, size=18)
            self.c.saveState()
            self.c.setStrokeColor(GOLD_DIM)
            self.c.setStrokeAlpha(0.3)
            self.c.setLineWidth(0.4)
            self.c.line(end_x, bar_y + bar_h + 7, end_x, bar_y + bar_h + 14)
            self.c.restoreState()

        elif pct_mode == "ring":
            avatar_y = cy + 8
            self._draw_hero_pct(W / 2, avatar_y - 6, pct_label, size=24)
            self.c.setFillColor(MUTED)
            self.c.setFont(FONT, 8)
            self.c.drawCentredString(W / 2, avatar_y - 20, "совместимость")
            self._draw_meter_labels(bar_x, bar_y, bar_w, bar_h)
            self._draw_glowing_bar(bar_x, bar_y, bar_w, bar_h, self.compat)

        return bar_y


def main() -> None:
    register_synastry_fonts()
    report = build_prototype_report()
    compat = overall_compatibility_pct(report)
    out = Path("docs/output/cover_compat_variants_v2.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)

    builder = CoverCompatPreviewBuilder(str(out), report)
    builder.compat = compat
    builder.page_num = 0
    builder._outline_root = False
    builder.build_variants()

    pct = int(round(compat * 100))
    print(f"PDF: {out}")
    print(f"Общая совместимость: {pct}%")
    for key, (title, desc, *_rest) in _VARIANT_META.items():
        print(f"  {key} — {title}: {desc}")


if __name__ == "__main__":
    main()
