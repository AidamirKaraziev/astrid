"""Сборка mobile-first PDF синастрии (ReportLab)."""

from __future__ import annotations

import math

from reportlab.lib import colors
from reportlab.pdfgen import canvas

from astra.reports.synastry.bot_link import resolve_telegram_bot_url
from astra.reports.synastry.theme import (
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
    GOLD,
    GOLD_DIM,
    GOLD_LIGHT,
    H,
    GLOW_STRENGTH,
    LEADING,
    LEGEND_ITEMS,
    MARGIN,
    MUTED,
    NEBULA_BLUE,
    NEBULA_PURPLE,
    PLANET_LABELS,
    TYPE,
    W,
    iter_cosmic_stars,
    person_initials,
    star_color,
)
from astra.reports.synastry.types import AspectData, PersonData, SynastryReportData


class SynastryPdfBuilder:
    def __init__(
        self,
        output_path: str,
        report: SynastryReportData,
        *,
        bot_username: str | None = None,
    ) -> None:
        self.c = canvas.Canvas(output_path, pagesize=(W, H))
        self.page_num = 0
        self.total_pages = 0
        self._outline_root = False
        self._y = 0.0
        self._report = report
        self._bot_username = bot_username

    def build(self) -> None:
        self.total_pages = self._simulate_page_count()

        self._page_cover()
        self._page_tldr()
        self._page_natal_both()
        remaining_strong = self._page_legend_and_strong_start()
        if remaining_strong:
            self._pack_aspect_pages(remaining_strong, section="Главные аспекты", hot=True)
        self._pack_aspect_pages(
            self._report.working_aspects,
            section="Рабочие аспекты",
            hot=False,
            intro=self._report.working_aspects_intro,
        )
        self._page_zones()
        self._page_conclusion()
        self.c.save()

    def _simulate_page_count(self) -> int:
        total = 5  # cover, tldr, natal, zones, conclusion
        total += 1  # legend + first strong batch

        y = self._content_top()
        y = y - self._legend_height() - GAP["sm"]
        y = y - self._aspect_card_height(self._report.strong_aspects[0], hot=True) - GAP["sm"]
        idx = 1
        while idx < len(self._report.strong_aspects):
            h = self._aspect_card_height(self._report.strong_aspects[idx], hot=True) + GAP["sm"]
            if y - h >= CONTENT_BOTTOM:
                y -= h
                idx += 1
            else:
                break
        total += len(self._plan_aspect_pages(self._report.strong_aspects[idx:]))
        total += len(self._plan_aspect_pages(self._report.working_aspects))
        return total

    def _plan_aspect_pages(self, aspects: tuple[AspectData, ...] | list[AspectData]) -> list[str]:
        if not aspects:
            return []
        pages: list[str] = []
        idx = 0
        while idx < len(aspects):
            y = self._content_top()
            count = 0
            while idx < len(aspects):
                h = self._aspect_card_height(aspects[idx], hot=False)
                need = h + (GAP["sm"] if count else 0)
                if count > 0 and y - need < CONTENT_BOTTOM:
                    break
                if count == 0 and y - need < CONTENT_BOTTOM:
                    pass
                y -= need
                count += 1
                idx += 1
            pages.append(f"asp-{idx}")
        return pages

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
            self.c.addOutlineEntry("Синастрия", bookmark, 0)
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
        pair = f"{self._report.person_a.name} × {self._report.person_b.name}"
        self.c.drawRightString(W - MARGIN, FOOTER_TOP - 18, pair)

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

    def _draw_telegram_cta_button(self, bottom: float) -> float:
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
        self.c.drawCentredString(cx, bottom + 17, self._report.cta_text)

        url = resolve_telegram_bot_url(self._bot_username)
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

    def _natal_block_height(self, person: PersonData) -> float:
        return 34 + len(person.planets) * 30 + 10

    def _draw_natal_block(self, y_top: float, person: PersonData) -> float:
        h = self._natal_block_height(person)
        bottom = y_top - h
        self._draw_card_bg(bottom, h, accent=person.accent, glow="section")
        self._draw_sparkle(W - MARGIN - 14, y_top - 14, 2, person.accent)

        ty = y_top - 20
        self.c.setFillColor(person.accent)
        self.c.setFont(FONT_BOLD, TYPE["body"])
        self.c.drawString(MARGIN + 12, ty, person.name)
        self.c.setFillColor(MUTED)
        self.c.setFont(FONT, TYPE["caption"])
        self.c.drawRightString(W - MARGIN - 12, ty, person.subtitle)

        row_y = ty - 22
        for key, sign in person.planets:
            label = PLANET_LABELS.get(key, key)
            self.c.setFillColor(MUTED)
            self.c.setFont(FONT, TYPE["body"])
            self.c.drawString(MARGIN + 12, row_y, label)
            self.c.setFillColor(CREAM)
            self.c.setFont(FONT_BOLD, TYPE["body"])
            self.c.drawRightString(W - MARGIN - 12, row_y, sign)
            row_y -= 30
        return bottom - GAP["sm"]

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

    # --- pages ---

    def _page_cover(self) -> None:
        self._new_page("cover", "Обложка")
        self._draw_bg(vibe="cover")
        self._draw_radial_glow(W / 2, H * 0.48, 160, GOLD, intensity="section")

        block_h = 340
        top = H - MARGIN - 50
        bottom = top - block_h
        self._draw_card_bg(bottom, block_h, accent=GOLD, glow="section")

        cy = bottom + block_h * 0.55
        self.c.saveState()
        self.c.setStrokeColor(GOLD_LIGHT)
        self.c.setStrokeAlpha(0.5)
        self.c.setLineWidth(0.5)
        self.c.circle(W / 2, cy, 88, fill=0, stroke=1)
        self.c.restoreState()
        self.c.setStrokeColor(GOLD_DIM)
        self.c.setLineWidth(0.3)
        self.c.circle(W / 2, cy, 96, fill=0, stroke=1)

        avatar_y = cy + 8
        for dx, person in [
            (-48, self._report.person_a),
            (48, self._report.person_b),
        ]:
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

        self._draw_sparkle(W / 2, avatar_y + 2, 3, GOLD_LIGHT)
        self.c.setFillColor(GOLD)
        self.c.setFont(FONT_BOLD, 14)
        self.c.drawCentredString(W / 2, avatar_y - 2, "×")

        self.c.setFillColor(GOLD_LIGHT)
        self.c.setFont(FONT_BOLD, TYPE["display"])
        self.c.drawCentredString(W / 2, cy + 108, "Синастрия")
        self.c.setFillColor(MUTED)
        self.c.setFont(FONT, TYPE["body"])
        self.c.drawCentredString(W / 2, cy + 86, "Совместимость пары")
        self.c.setFont(FONT, TYPE["caption"])
        self.c.drawCentredString(W / 2, cy - 58, self._report.person_a.subtitle)
        self.c.drawCentredString(W / 2, cy - 74, self._report.person_b.subtitle)

        self.c.setFillColor(GOLD)
        self.c.setFont(FONT, TYPE["caption"])
        self.c.drawCentredString(W / 2, bottom + 16, f"✦  {self._report.read_time_label}  ✦")

        self._draw_footer()

    def _page_tldr(self) -> None:
        self._new_page("tldr", "Краткий итог")
        self._draw_bg(vibe="content")
        self._draw_page_header("Краткий итог", "Главное за 30 секунд")
        self._draw_radial_glow(W / 2, self._y - 40, 90, GOLD, intensity="card")

        tldr = self._report.tldr
        pad = 12
        text_w = CONTENT_W - 2 * pad
        box_h = self._text_height(tldr, text_w) + 2 * pad
        bottom = self._y - box_h
        self._draw_card_bg(bottom, box_h, accent=GOLD, glow="section")
        self._draw_text_block(tldr, MARGIN + pad, self._y - pad, text_w)
        self._y = bottom - GAP["md"]

        self.c.setFillColor(GOLD_LIGHT)
        self.c.setFont(FONT_BOLD, TYPE["body"])
        self.c.drawString(MARGIN, self._y, "✦  Оценка")
        self._y -= GAP["md"]

        for metric in self._report.metrics:
            self._y = self._draw_progress_bar(self._y, metric.label, metric.value, metric.color)

        self._draw_footer()

    def _page_natal_both(self) -> None:
        self._new_page("natal", "Натальные данные")
        self._draw_bg(vibe="content")
        self._draw_page_header("Натальные данные", "Планеты в знаках")

        self._y = self._draw_natal_block(self._y, self._report.person_a)
        self._y = self._draw_natal_block(self._y, self._report.person_b)

        insight = self._report.natal_insight
        pad = 12
        text_w = CONTENT_W - 2 * pad
        box_h = self._text_height(insight, text_w, size=TYPE["caption"], leading=LEADING["caption"]) + 2 * pad
        if self._fits(box_h):
            bottom = self._y - box_h
            self._draw_card_bg(bottom, box_h, accent=GOLD_DIM, glow="card")
            self._draw_text_block(
                insight, MARGIN + pad, self._y - pad, text_w,
                size=TYPE["caption"], leading=LEADING["caption"], color=MUTED,
            )
            self._y = bottom

        self._draw_footer()

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

    def _page_legend_and_strong_start(self) -> tuple[AspectData, ...]:
        self._new_page("strong", "Главные аспекты")
        self._draw_bg(vibe="content")
        self._draw_page_header("Главные аспекты", "Орб < 2° — работают постоянно")

        self._y = self._draw_legend(self._y)
        self._y = self._draw_aspect_card(self._y, self._report.strong_aspects[0], hot=True)

        idx = 1
        while idx < len(self._report.strong_aspects):
            h = self._aspect_card_height(self._report.strong_aspects[idx], hot=True) + GAP["sm"]
            if not self._fits(h):
                break
            self._y = self._draw_aspect_card(self._y, self._report.strong_aspects[idx], hot=True)
            idx += 1

        self._draw_footer()
        return self._report.strong_aspects[idx:]

    def _pack_aspect_pages(
        self,
        aspects: tuple[AspectData, ...] | list[AspectData],
        *,
        section: str,
        hot: bool,
        intro: str = "",
    ) -> None:
        if not aspects:
            return
        idx = 0
        page_no = 0
        while idx < len(aspects):
            bookmark = f"{section}-{page_no}"
            subtitle = intro if page_no == 0 and intro else ""
            if page_no > 0:
                subtitle = "продолжение"
            self._new_page(bookmark, section if page_no == 0 else f"{section} (прод.)")
            self._draw_bg(vibe="content")
            self._draw_page_header(section, subtitle)

            placed = 0
            while idx < len(aspects):
                h = self._aspect_card_height(aspects[idx], hot=hot)
                gap = GAP["sm"] if placed else 0
                if placed > 0 and not self._fits(h + gap):
                    break
                if placed == 0 and not self._fits(h):
                    pass
                self._y -= gap
                self._y = self._draw_aspect_card(self._y, aspects[idx], hot=hot)
                idx += 1
                placed += 1
            self._draw_footer()
            page_no += 1

    def _page_zones(self) -> None:
        self._new_page("zones", "Итог по зонам")
        self._draw_bg(vibe="content")
        self._draw_page_header("Итог по зонам")

        for zone in self._report.zone_blocks:
            items = list(zone.items)
            h = self._zone_block_height(items)
            if not self._fits(h):
                self._draw_footer()
                self._new_page("zones-cont", "Итог по зонам (прод.)")
                self._draw_bg(vibe="content")
                self._draw_page_header("Итог по зонам", "продолжение")
            self._y = self._draw_zone_block(self._y, zone.title, zone.color, items)

        self._draw_footer()

    def _page_conclusion(self) -> None:
        self._new_page("conclusion", "Вывод")
        self._draw_bg(vibe="finale")
        self._draw_radial_glow(W / 2, H * 0.55, 220, GOLD, intensity="finale")

        quote = self._report.conclusion_quote
        tip = self._report.conclusion_tip

        pad = 16
        inner_w = CONTENT_W - 2 * pad
        tip_label_h = 28
        tip_body_h = self._text_height(tip, inner_w - 8, size=TYPE["body"], leading=LEADING["body"])
        quote_h = self._text_height(
            quote, inner_w, size=TYPE["quote"], leading=LEADING["body"] + 2,
        )
        card_h = pad + quote_h + GAP["lg"] + tip_label_h + tip_body_h + pad

        title_y = H - MARGIN - 22
        self._draw_sparkle(MARGIN + 8, title_y - 4, 4)
        self._draw_sparkle(W - MARGIN - 8, title_y - 4, 4)
        self.c.setFillColor(GOLD_LIGHT)
        self.c.setFont(FONT_BOLD, TYPE["h1"])
        self.c.drawCentredString(W / 2, title_y, "ВЫВОД")
        self.c.setFillColor(MUTED)
        self.c.setFont(FONT, TYPE["caption"])
        self.c.drawCentredString(W / 2, title_y - 18, "главная мысль для пары")
        self.c.setStrokeColor(GOLD_DIM)
        self.c.setLineWidth(0.6)
        self.c.line(W / 2 - 56, title_y - 26, W / 2 + 56, title_y - 26)

        card_top = title_y - 40
        card_bottom = card_top - card_h
        card_x = MARGIN
        self._draw_glowing_round_rect(card_x, card_bottom, CONTENT_W, card_h, radius=14)

        qy = card_top - pad
        self.c.setFillColor(GOLD)
        self.c.setFont(FONT_BOLD, 22)
        self.c.drawString(card_x + pad, qy, "“")
        qy = self._draw_text_block(
            quote,
            card_x + pad,
            qy - 8,
            inner_w,
            size=TYPE["quote"],
            leading=LEADING["body"] + 2,
            color=CREAM,
        )

        tip_box_top = qy - GAP["lg"]
        tip_box_h = tip_label_h + tip_body_h + 10
        tip_box_bottom = tip_box_top - tip_box_h
        self.c.saveState()
        self.c.setFillColor(GOLD)
        self.c.setFillAlpha(0.12)
        self.c.roundRect(card_x + pad - 4, tip_box_bottom, inner_w + 8, tip_box_h, 8, fill=1, stroke=0)
        self.c.restoreState()
        self.c.setStrokeColor(GOLD)
        self.c.setLineWidth(0.7)
        self.c.roundRect(card_x + pad - 4, tip_box_bottom, inner_w + 8, tip_box_h, 8, fill=0, stroke=1)

        self.c.setFillColor(BG_DARK)
        self.c.roundRect(card_x + pad + 2, tip_box_top - 20, 132, 18, 6, fill=1, stroke=0)
        self.c.setFillColor(GOLD_LIGHT)
        self.c.setFont(FONT_BOLD, TYPE["caption"])
        self.c.drawString(card_x + pad + 10, tip_box_top - 16, "✦  Практика на неделю")

        self._draw_text_block(
            tip,
            card_x + pad + 4,
            tip_box_top - 38,
            inner_w - 8,
            size=TYPE["body"],
            color=CREAM,
        )

        mid_x = W / 2
        self._draw_gold_radial_glow(mid_x, card_bottom + 24, 55)
        for dx, tone in [(-52, GOLD_DIM), (0, GOLD_LIGHT), (52, GOLD_DIM)]:
            self._draw_sparkle(mid_x + dx, card_bottom + 10, 3, tone)

        btn_bottom = card_bottom - CTA_BUTTON_H - GAP["lg"]
        if btn_bottom < CONTENT_BOTTOM + 18:
            btn_bottom = CONTENT_BOTTOM + 18
        self._draw_telegram_cta_button(btn_bottom)

        self.c.setFillColor(GOLD)
        self.c.setFont(FONT, TYPE["caption"])
        self.c.drawCentredString(W / 2, btn_bottom - 14, "Сделано в Astra ✨")
        self._draw_footer()

