"""Общие примитивы mobile-first PDF-отчётов Astra (ReportLab).

Извлечено из SynastryPdfBuilder без изменений логики: фон, звёзды, карточки,
глоу, футер, текстовые блоки, карточки аспектов, легенда, CTA-кнопка.
Отчёты (синастрия, натал) наследуются и добавляют свои страницы.
"""

from __future__ import annotations

import math

from reportlab.lib import colors
from reportlab.pdfgen import canvas

from astra.reports.bot_link import resolve_telegram_bot_url
from astra.reports.theme import (
    ASPECT_STYLES,
    BG_CARD,
    BG_CARD_DEEP,
    BG_DARK,
    CONTENT_BOTTOM,
    CONTENT_W,
    CREAM,
    CTA_BUTTON_H,
    FINALE_RING_MUL,
    FONT,
    FONT_BOLD,
    FOOTER_TOP,
    GAP,
    GLOW_STRENGTH,
    GOLD,
    GOLD_DIM,
    GOLD_LIGHT,
    H,
    LEADING,
    LEGEND_ITEMS,
    MARGIN,
    MUTED,
    NEBULA_BLUE,
    NEBULA_PURPLE,
    TYPE,
    W,
    iter_cosmic_stars,
    star_color,
)
from astra.reports.types import AspectData


class BasePdfBuilder:
    outline_root_title = "Astra"

    def __init__(
        self,
        output_path: str,
        *,
        bot_username: str | None = None,
        referral_code: str | None = None,
    ) -> None:
        self.c = canvas.Canvas(output_path, pagesize=(W, H))
        self.page_num = 0
        self.total_pages = 0
        self._outline_root = False
        self._y = 0.0
        self._bot_username = bot_username
        self._referral_code = referral_code

    def _footer_right_text(self) -> str:
        return ""

    def _content_top(self) -> float:
        return H - MARGIN - 46

    # --- primitives ---

    def _new_page(self, bookmark: str, outline_title: str | None = None) -> None:
        if self.page_num > 0:
            self.c.showPage()
        self.page_num += 1
        self.c.bookmarkPage(bookmark)
        title = outline_title or bookmark
        if not self._outline_root:
            self.c.addOutlineEntry(self.outline_root_title, bookmark, 0)
            self._outline_root = True
        self.c.addOutlineEntry(title, bookmark, 1)
        self._y = self._content_top()

    def _draw_bg(self, *, vibe: str = "content") -> None:
        self.c.setFillColor(BG_DARK)
        self.c.rect(0, 0, W, H, fill=1, stroke=0)

        # Лёгкий космический градиент сверху
        self.c.saveState()
        self.c.setFillColor(colors.HexColor("#141428"))
        self.c.setFillAlpha(0.55)
        self.c.rect(0, H * 0.45, W, H * 0.55, fill=1, stroke=0)
        self.c.restoreState()

        neb_int = "section" if vibe in {"finale", "cover"} else "card"
        self._draw_radial_glow(-10, H + 10, 150, NEBULA_PURPLE, intensity=neb_int)
        self._draw_radial_glow(W + 10, H * 0.3, 120, NEBULA_BLUE, intensity=neb_int)
        if vibe == "finale":
            self._draw_radial_glow(W / 2, H * 0.72, 180, GOLD_DIM, intensity="section")

        self._draw_cosmic_starfield(rich=vibe == "finale")

    def _draw_cosmic_star(self, kind: str, cx: float, cy: float, size: float, alpha: float, color: colors.Color) -> None:
        self.c.saveState()
        self.c.setFillColor(color)
        self.c.setStrokeColor(color)

        if kind == "dot":
            self.c.setFillAlpha(alpha)
            self.c.circle(cx, cy, size, fill=1, stroke=0)
            if alpha > 0.5:
                self.c.setFillAlpha(alpha * 0.25)
                self.c.circle(cx, cy, size * 2.2, fill=1, stroke=0)
        elif kind == "sparkle":
            self.c.setStrokeAlpha(alpha)
            self.c.setLineWidth(max(0.55, size * 0.18))
            for i in range(4):
                angle = math.pi / 4 * i
                self.c.line(
                    cx + math.cos(angle) * size,
                    cy + math.sin(angle) * size,
                    cx - math.cos(angle) * size,
                    cy - math.sin(angle) * size,
                )
            self.c.setFillAlpha(alpha)
            self.c.circle(cx, cy, size * 0.28, fill=1, stroke=0)
            self.c.setFillAlpha(alpha * 0.2)
            self.c.circle(cx, cy, size * 1.1, fill=1, stroke=0)
        elif kind == "plus":
            self.c.setStrokeAlpha(alpha)
            self.c.setLineWidth(max(0.9, size * 0.32))
            self.c.setLineCap(1)  # round
            self.c.line(cx, cy - size, cx, cy + size)
            self.c.line(cx - size, cy, cx + size, cy)
            self.c.setFillAlpha(alpha * 0.85)
            self.c.circle(cx, cy, size * 0.2, fill=1, stroke=0)
        elif kind == "diamond":
            self.c.setStrokeAlpha(alpha)
            self.c.setLineWidth(max(0.6, size * 0.22))
            for angle_off in (0, math.pi / 2):
                a = angle_off
                self.c.line(cx + math.cos(a) * size, cy + math.sin(a) * size * 0.55,
                            cx - math.cos(a) * size, cy - math.sin(a) * size * 0.55)
            self.c.setFillAlpha(alpha)
            self.c.circle(cx, cy, size * 0.22, fill=1, stroke=0)
        self.c.restoreState()

    def _draw_cosmic_starfield(self, *, rich: bool = False) -> None:
        for kind, sx, sy, size, alpha, color_key in iter_cosmic_stars(rich=rich):
            color = star_color(color_key)
            a = min(1.0, alpha * (1.25 if rich else 1.0))
            s = size * (1.15 if rich and kind != "dot" else 1.0)
            self._draw_cosmic_star(kind, sx, sy, s, a, color)

    def _draw_footer(self) -> None:
        self.c.setFillColor(MUTED)
        self.c.setFont(FONT, TYPE["caption"])
        self.c.drawCentredString(W / 2, FOOTER_TOP - 18, f"{self.page_num} / {self.total_pages}")
        self.c.drawString(MARGIN, FOOTER_TOP - 18, "Astra")
        self.c.drawRightString(W - MARGIN, FOOTER_TOP - 18, self._footer_right_text())

    def _draw_page_header(self, title: str, subtitle: str = "") -> None:
        y = H - MARGIN
        self._draw_sparkle(MARGIN + 2, y - 10, 2.5, GOLD_DIM)
        self.c.setFillColor(GOLD_LIGHT)
        self.c.setFont(FONT_BOLD, TYPE["h2"])
        self.c.drawString(MARGIN + 14, y - 18, title)
        if subtitle:
            self.c.setFillColor(MUTED)
            self.c.setFont(FONT, TYPE["caption"])
            self.c.drawString(MARGIN + 14, y - 34, subtitle)
        line_y = y - 42 if subtitle else y - 26
        self.c.saveState()
        self.c.setStrokeColor(GOLD)
        self.c.setStrokeAlpha(0.35)
        self.c.setLineWidth(0.8)
        self.c.line(MARGIN, line_y, W - MARGIN, line_y)
        self.c.restoreState()
        self.c.setStrokeColor(colors.HexColor("#2A2A42"))
        self.c.setLineWidth(0.4)
        self.c.line(MARGIN, line_y - 2, W - MARGIN, line_y - 2)
        self._y = line_y - GAP["md"]

    def _wrap_lines(
        self,
        text: str,
        max_width: float,
        *,
        font: str = FONT,
        size: int = TYPE["body"],
    ) -> list[str]:
        words = text.split()
        line = ""
        lines: list[str] = []
        for word in words:
            test = f"{line} {word}".strip()
            if self.c.stringWidth(test, font, size) <= max_width:
                line = test
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)
        return lines or [""]

    def _text_height(
        self,
        text: str,
        max_width: float,
        *,
        font: str = FONT,
        size: int = TYPE["body"],
        leading: int = LEADING["body"],
    ) -> float:
        return len(self._wrap_lines(text, max_width, font=font, size=size)) * leading

    def _draw_text_block(
        self,
        text: str,
        x: float,
        y: float,
        max_width: float,
        *,
        font: str = FONT,
        size: int = TYPE["body"],
        leading: int = LEADING["body"],
        color: colors.Color = CREAM,
    ) -> float:
        lines = self._wrap_lines(text, max_width, font=font, size=size)
        for i, ln in enumerate(lines):
            self.c.setFillColor(color)
            self.c.setFont(font, size)
            self.c.drawString(x, y - i * leading, ln)
        return y - len(lines) * leading

    def _draw_card_bg(
        self,
        bottom: float,
        height: float,
        *,
        accent: colors.Color | None = None,
        glow: str = "card",
    ) -> None:
        x, w = MARGIN, CONTENT_W
        tone = accent or GOLD
        cx = x + w / 2
        cy = bottom + height / 2
        self._draw_radial_glow(cx, cy, max(w, height) * 0.52, tone, intensity=glow)

        scale, alpha_mul = GLOW_STRENGTH[glow]
        ring_sets = {
            "card": ((7, 0.10), (3, 0.16)),
            "section": ((10, 0.14), (4, 0.22)),
            "finale": ((14, 0.12), (6, 0.20), (2, 0.32)),
        }
        rings = ring_sets.get(glow, ring_sets["card"])
        for expand, alpha in rings:
            self.c.saveState()
            self.c.setStrokeColor(GOLD_LIGHT if tone == GOLD else tone)
            ring_alpha = min(1.0, alpha * alpha_mul)
            self.c.setStrokeAlpha(ring_alpha)
            self.c.setLineWidth(0.8 if glow == "finale" else 0.7)
            self.c.roundRect(
                x - expand, bottom - expand, w + 2 * expand, height + 2 * expand,
                8 + expand * 0.25, fill=0, stroke=1,
            )
            self.c.restoreState()

        self.c.setFillColor(BG_CARD)
        self.c.roundRect(x, bottom, w, height, 8, fill=1, stroke=0)
        if accent is not None:
            self.c.setFillColor(accent)
            self.c.roundRect(x, bottom, 4, height, 2, fill=1, stroke=0)
        self.c.saveState()
        self.c.setStrokeColor(tone)
        border_alpha = 0.35 if glow == "finale" else (0.28 if glow == "section" else 0.22)
        self.c.setStrokeAlpha(border_alpha)
        self.c.setLineWidth(0.6)
        self.c.roundRect(x, bottom, w, height, 8, fill=0, stroke=1)
        self.c.restoreState()

    def _fits(self, height: float) -> bool:
        return self._y - height >= CONTENT_BOTTOM

    # --- blocks ---

    def _progress_bar_height(self) -> float:
        return 36

    def _draw_sparkle(self, cx: float, cy: float, size: float, color: colors.Color = GOLD) -> None:
        self.c.setStrokeColor(color)
        self.c.setFillColor(color)
        for i in range(4):
            angle = math.pi / 4 * i
            self.c.setLineWidth(0.7)
            self.c.line(
                cx + math.cos(angle) * size,
                cy + math.sin(angle) * size,
                cx - math.cos(angle) * size,
                cy - math.sin(angle) * size,
            )
        self.c.circle(cx, cy, size * 0.22, fill=1, stroke=0)

    def _draw_radial_glow(
        self,
        cx: float,
        cy: float,
        max_r: float,
        tone: colors.Color,
        *,
        intensity: str = "card",
    ) -> None:
        scale, alpha_mul = GLOW_STRENGTH[intensity]
        r = max_r * scale
        layers = (
            (r, 0.075, tone),
            (r * 0.68, 0.095, GOLD if tone != GOLD else GOLD_LIGHT),
            (r * 0.42, 0.08, tone),
            (r * 0.22, 0.06, GOLD_LIGHT),
        )
        for radius, alpha, color in layers:
            self.c.saveState()
            self.c.setFillColor(color)
            self.c.setFillAlpha(min(1.0, alpha * alpha_mul))
            self.c.circle(cx, cy, radius, fill=1, stroke=0)
            self.c.restoreState()

    def _draw_gold_radial_glow(self, cx: float, cy: float, max_r: float) -> None:
        self._draw_radial_glow(cx, cy, max_r, GOLD, intensity="finale")
        extra = (
            (max_r * 0.85, 0.14, GOLD_DIM),
            (max_r * 0.72, 0.16, GOLD),
            (max_r * 0.48, 0.18, GOLD_LIGHT),
            (max_r * 0.28, 0.12, GOLD),
        )
        for radius, alpha, color in extra:
            self.c.saveState()
            self.c.setFillColor(color)
            self.c.setFillAlpha(min(1.0, alpha * FINALE_RING_MUL * 0.5))
            self.c.circle(cx, cy, radius, fill=1, stroke=0)
            self.c.restoreState()

    def _draw_glowing_round_rect(
        self,
        x: float,
        bottom: float,
        width: float,
        height: float,
        *,
        radius: float = 12,
    ) -> None:
        cx = x + width / 2
        cy = bottom + height / 2
        self._draw_gold_radial_glow(cx, cy, max(width, height) * 0.68)

        for expand, alpha, lw in ((18, 0.12, 0.7), (10, 0.18, 0.9), (4, 0.32, 1.2)):
            self.c.saveState()
            self.c.setStrokeColor(GOLD_LIGHT)
            self.c.setStrokeAlpha(min(1.0, alpha * FINALE_RING_MUL * 0.5))
            self.c.setLineWidth(lw)
            self.c.roundRect(
                x - expand,
                bottom - expand,
                width + 2 * expand,
                height + 2 * expand,
                radius + expand * 0.3,
                fill=0,
                stroke=1,
            )
            self.c.restoreState()

        self.c.setFillColor(BG_CARD_DEEP)
        self.c.setStrokeColor(GOLD)
        self.c.setLineWidth(1.2)
        self.c.roundRect(x, bottom, width, height, radius, fill=1, stroke=1)

    def _draw_telegram_cta_button(self, bottom: float, text: str) -> float:
        """Золотая кнопка-ссылка на Telegram-бота."""
        btn_w = CONTENT_W
        btn_x = MARGIN
        btn_h = CTA_BUTTON_H
        cx = btn_x + btn_w / 2
        cy = bottom + btn_h / 2

        self._draw_radial_glow(cx, cy, btn_w * 0.48, GOLD, intensity="section")
        for expand, alpha in ((8, 0.14), (3, 0.24)):
            self.c.saveState()
            self.c.setStrokeColor(GOLD_LIGHT)
            self.c.setStrokeAlpha(alpha)
            self.c.setLineWidth(0.9)
            self.c.roundRect(
                btn_x - expand, bottom - expand, btn_w + 2 * expand, btn_h + 2 * expand,
                btn_h / 2 + expand * 0.2, fill=0, stroke=1,
            )
            self.c.restoreState()

        self.c.setFillColor(GOLD)
        self.c.roundRect(btn_x, bottom, btn_w, btn_h, btn_h / 2, fill=1, stroke=0)
        self.c.setFillColor(BG_DARK)
        self.c.setFont(FONT_BOLD, TYPE["body"])
        self.c.drawCentredString(cx, bottom + 17, text)

        url = resolve_telegram_bot_url(self._bot_username, self._referral_code)
        self.c.linkURL(
            url,
            (btn_x, bottom, btn_x + btn_w, bottom + btn_h),
            relative=0,
            thickness=0,
            color=None,
        )
        return bottom

    def _draw_progress_bar(self, y: float, label: str, pct: float, color: colors.Color) -> float:
        self.c.setFillColor(CREAM)
        self.c.setFont(FONT, TYPE["body"])
        self.c.drawString(MARGIN, y, label)
        self.c.setFont(FONT_BOLD, TYPE["body"])
        self.c.drawRightString(W - MARGIN, y, f"{int(pct * 100)}%")
        bar_y = y - 20
        self.c.setFillColor(colors.HexColor("#252538"))
        self.c.roundRect(MARGIN, bar_y, CONTENT_W, 10, 5, fill=1, stroke=0)
        if pct > 0:
            self._draw_radial_glow(
                MARGIN + CONTENT_W * pct * 0.5, bar_y + 5, CONTENT_W * pct * 0.55, color, intensity="card",
            )
            self.c.setFillColor(color)
            self.c.roundRect(MARGIN, bar_y, CONTENT_W * pct, 10, 5, fill=1, stroke=0)
        return bar_y - GAP["md"]

    def _aspect_card_height(self, asp: AspectData, *, hot: bool) -> float:
        pad = 12
        text_w = CONTENT_W - 2 * pad
        headline_h = self._text_height(asp.headline, text_w, font=FONT_BOLD, size=TYPE["body"])
        body_h = self._text_height(asp.body, text_w, size=TYPE["body"], leading=LEADING["caption"])
        return 46 + headline_h + body_h + pad

    def _draw_aspect_card(self, y_top: float, asp: AspectData, *, hot: bool) -> float:
        col, sym, label = ASPECT_STYLES.get(asp.aspect_type, (MUTED, "?", asp.aspect_type))
        pad = 12
        text_w = CONTENT_W - 2 * pad
        h = self._aspect_card_height(asp, hot=hot)
        bottom = y_top - h
        self._draw_card_bg(bottom, h, accent=col, glow="section" if hot else "card")

        self.c.setFillColor(col)
        self.c.setFont(FONT_BOLD, 18)
        self.c.drawString(MARGIN + pad, y_top - 22, sym)
        self.c.setFont(FONT_BOLD, TYPE["body"])
        self.c.drawString(MARGIN + pad + 24, y_top - 22, label)
        self.c.setFillColor(MUTED)
        self.c.setFont(FONT, TYPE["caption"])
        self.c.drawRightString(W - MARGIN - pad, y_top - 22, f"орб {asp.orb}°")

        if hot:
            self.c.setFillColor(col)
            self.c.roundRect(W - MARGIN - pad - 82, y_top - 38, 82, 16, 5, fill=1, stroke=0)
            self.c.setFillColor(BG_DARK)
            self.c.setFont(FONT_BOLD, 8)
            self.c.drawCentredString(W - MARGIN - pad - 41, y_top - 34, asp.strength)

        self.c.setFillColor(MUTED)
        self.c.setFont(FONT, TYPE["caption"])
        self.c.drawString(MARGIN + pad, y_top - 38, f"{asp.from_planet}  →  {asp.to_planet}")

        hy = y_top - 52
        hy = self._draw_text_block(
            asp.headline, MARGIN + pad, hy, text_w, font=FONT_BOLD, size=TYPE["body"]
        )
        self._draw_text_block(
            asp.body,
            MARGIN + pad,
            hy - GAP["xs"],
            text_w,
            size=TYPE["body"],
            leading=LEADING["caption"],
            color=MUTED,
        )
        return bottom - GAP["sm"]

    def _zone_block_height(self, items: list[str]) -> float:
        text_w = CONTENT_W - 36
        total = 28
        for item in items:
            total += self._text_height(item, text_w) + GAP["xs"]
        return total + 8

    def _draw_zone_block(self, y_top: float, title: str, color: colors.Color, items: list[str]) -> float:
        h = self._zone_block_height(items)
        bottom = y_top - h
        self._draw_card_bg(bottom, h, accent=color, glow="section")
        self.c.setFillColor(color)
        self.c.setFont(FONT_BOLD, TYPE["body"])
        self.c.drawString(MARGIN + 12, y_top - 18, title)
        iy = y_top - 36
        text_w = CONTENT_W - 36
        for item in items:
            self.c.setFillColor(color)
            self.c.circle(MARGIN + 16, iy + 5, 2.5, fill=1, stroke=0)
            iy = self._draw_text_block(item, MARGIN + 26, iy, text_w, size=TYPE["body"]) - GAP["xs"]
        return bottom - GAP["sm"]

    def _legend_height(self) -> float:
        rows = (len(LEGEND_ITEMS) + 1) // 2
        return rows * 34 + 28

    def _draw_legend(self, y_top: float) -> float:
        h = self._legend_height()
        bottom = y_top - h
        self._draw_card_bg(bottom, h, glow="card")
        self.c.setFillColor(MUTED)
        self.c.setFont(FONT, TYPE["caption"])
        self.c.drawString(MARGIN + 12, y_top - 16, "✦  Как читать · меньший орб = сильнее")

        col_w = (CONTENT_W - 24) / 2
        x0 = MARGIN + 12
        y = y_top - 34
        for i, (col, title, hint) in enumerate(LEGEND_ITEMS):
            cx = x0 + (i % 2) * (col_w + 8)
            if i % 2 == 0 and i > 0:
                y -= 34
            self.c.setFillColor(col)
            self.c.setFont(FONT_BOLD, TYPE["caption"])
            self.c.drawString(cx, y, title)
            self.c.setFillColor(MUTED)
            self.c.drawString(cx, y - 13, hint)
        return bottom - GAP["sm"]
