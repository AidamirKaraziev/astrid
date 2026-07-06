"""Сборка mobile-first PDF синастрии (ReportLab).

Общие примитивы (фон, карточки, аспекты, легенда) — в BasePdfBuilder.
"""

from __future__ import annotations

from reportlab.lib import colors

from astra.reports.base_builder import BasePdfBuilder
from astra.reports.synastry.theme import (
    BG_DARK,
    CONTENT_BOTTOM,
    CONTENT_W,
    CREAM,
    CTA_BUTTON_H,
    FONT,
    FONT_BOLD,
    GAP,
    GOLD,
    GOLD_DIM,
    GOLD_LIGHT,
    H,
    LEADING,
    MARGIN,
    MUTED,
    PLANET_LABELS,
    TYPE,
    W,
    person_initials,
)
from astra.reports.synastry.types import AspectData, PersonData, SynastryReportData

_COVER_TRACK = colors.HexColor("#252538")
_COVER_BLOCK_H = 448.0
_COVER_METER_BAR_OFFSET = 108.0
_COVER_GAP_METER_TO_BIRTH = 28.0
_COVER_GAP_BIRTH_TO_READ = 20.0


def _overall_compatibility(report: SynastryReportData) -> float:
    if not report.metrics:
        return 0.0
    return sum(m.value for m in report.metrics) / len(report.metrics)


def _format_birth_line(subtitle: str) -> str:
    parts = [p.strip() for p in subtitle.split("·")]
    if len(parts) >= 3:
        return f"{parts[0]} · {parts[1]} · {parts[2]}"
    if len(parts) == 2:
        return f"{parts[0]} · {parts[1]}"
    return subtitle


class SynastryPdfBuilder(BasePdfBuilder):
    outline_root_title = "Синастрия"

    def __init__(
        self,
        output_path: str,
        report: SynastryReportData,
        *,
        bot_username: str | None = None,
    ) -> None:
        super().__init__(output_path, bot_username=bot_username)
        self._report = report

    def _footer_right_text(self) -> str:
        return f"{self._report.person_a.name} × {self._report.person_b.name}"

    def build(self) -> None:
        self.total_pages = self._simulate_page_count()

        self._page_cover()
        self._page_tldr()
        if self._report.pair_story.strip():
            self._page_pair_story()
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
        if self._report.pair_story.strip():
            total += 1
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

    # --- blocks ---

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

    def _draw_cover_zone_divider(self, y: float) -> None:
        self.c.saveState()
        self.c.setStrokeColor(GOLD_DIM)
        self.c.setStrokeAlpha(0.2)
        self.c.setLineWidth(0.5)
        self.c.line(MARGIN + 24, y, W - MARGIN - 24, y)
        self.c.restoreState()

    def _draw_compat_glowing_bar(self, x: float, y: float, width: float, height: float, pct: float) -> None:
        r = height / 2
        self.c.setFillColor(_COVER_TRACK)
        self.c.roundRect(x, y, width, height, r, fill=1, stroke=0)
        fill_w = max(height, width * pct)
        if pct <= 0:
            return

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

    def _draw_compat_meter_labels(self, bar_x: float, bar_y: float, bar_w: float, bar_h: float) -> None:
        self.c.setFillColor(MUTED)
        self.c.setFont(FONT, 9)
        self.c.drawCentredString(W / 2, bar_y + bar_h + 14, "общая совместимость")
        self.c.setFillColor(GOLD_DIM)
        self.c.setFont(FONT, 8)
        self.c.drawString(bar_x, bar_y - 11, "0")
        self.c.drawRightString(bar_x + bar_w, bar_y - 11, "100")

    def _draw_compat_hero_pct(self, cx: float, cy: float, pct_label: int, *, size: int = 34) -> None:
        num_w = self.c.stringWidth(str(pct_label), FONT_BOLD, size)
        pct_w = self.c.stringWidth("%", FONT_BOLD, 13)
        x0 = cx - (num_w + pct_w + 2) / 2
        self.c.setFillColor(GOLD_LIGHT)
        self.c.setFont(FONT_BOLD, size)
        self.c.drawString(x0, cy, str(pct_label))
        self.c.setFillColor(GOLD)
        self.c.setFont(FONT_BOLD, 13)
        self.c.drawString(x0 + num_w + 2, cy + size * 0.28, "%")

    # --- pages ---

    def _page_cover(self) -> None:
        self._new_page("cover", "Обложка")
        self._draw_bg(vibe="cover")

        block_h = _COVER_BLOCK_H
        top = H - MARGIN - 48
        bottom = top - block_h
        self._draw_radial_glow(W / 2, H * 0.46, 150, GOLD, intensity="section")
        self._draw_card_bg(bottom, block_h, accent=GOLD, glow="section")

        cy = bottom + block_h * 0.60
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

        self._draw_sparkle(W / 2, avatar_y + 2, 3, GOLD_LIGHT)
        self.c.setFillColor(GOLD)
        self.c.setFont(FONT_BOLD, 14)
        self.c.drawCentredString(W / 2, avatar_y - 2, "×")

        compat = _overall_compatibility(self._report)
        pct_label = int(round(compat * 100))
        bar_w = CONTENT_W - 56
        bar_x = MARGIN + 28
        bar_h = 7.0
        bar_y = bottom + _COVER_METER_BAR_OFFSET

        names_bottom = cy + 8 - 40 - 11
        self._draw_cover_zone_divider(names_bottom - 20)

        self._draw_compat_hero_pct(W / 2, bar_y + 40, pct_label)
        self._draw_compat_meter_labels(bar_x, bar_y, bar_w, bar_h)
        self._draw_compat_glowing_bar(bar_x, bar_y, bar_w, bar_h, compat)

        y_a = bar_y - _COVER_GAP_METER_TO_BIRTH
        y_b = y_a - 16
        self.c.setFont(FONT, TYPE["caption"])
        self.c.setFillColor(MUTED)
        self.c.drawCentredString(W / 2, y_a, _format_birth_line(self._report.person_a.subtitle))
        self.c.drawCentredString(W / 2, y_b, _format_birth_line(self._report.person_b.subtitle))

        read_y = bar_y - _COVER_GAP_METER_TO_BIRTH - _COVER_GAP_BIRTH_TO_READ - 32
        self.c.setFillColor(GOLD)
        self.c.setFont(FONT, TYPE["caption"])
        self.c.drawCentredString(W / 2, read_y, f"✦  {self._report.read_time_label}  ✦")

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

    def _page_pair_story(self) -> None:
        self._new_page("story", "История пары")
        self._draw_bg(vibe="content")
        self._draw_page_header("История пары", "Как вы звучите вместе")
        self._draw_radial_glow(W / 2, self._y - 50, 100, GOLD, intensity="section")

        paragraphs = [p.strip() for p in self._report.pair_story.split("\n\n") if p.strip()]
        pad = 14
        text_w = CONTENT_W - 2 * pad

        for idx, paragraph in enumerate(paragraphs):
            box_h = self._text_height(paragraph, text_w, leading=LEADING["body"]) + 2 * pad
            if not self._fits(box_h + GAP["sm"]) and idx > 0:
                self._draw_footer()
                self._new_page("story-cont", "История пары")
                self._draw_bg(vibe="content")
                self._draw_page_header("История пары", "продолжение")

            bottom = self._y - box_h
            glow = "section" if idx == 0 else "card"
            self._draw_card_bg(bottom, box_h, accent=GOLD if idx == 0 else None, glow=glow)
            color = CREAM if idx == 0 else MUTED
            size = TYPE["body"] if idx == 0 else TYPE["body"]
            self._draw_text_block(
                paragraph,
                MARGIN + pad,
                self._y - pad,
                text_w,
                size=size,
                leading=LEADING["body"],
                color=color,
            )
            self._y = bottom - GAP["md"]

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
        self._draw_telegram_cta_button(btn_bottom, self._report.cta_text)

        self.c.setFillColor(GOLD)
        self.c.setFont(FONT, TYPE["caption"])
        self.c.drawCentredString(W / 2, btn_bottom - 14, "Сделано в Astra ✨")
        self._draw_footer()
