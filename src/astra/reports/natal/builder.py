"""Сборка mobile-first PDF разбора натальной карты (ReportLab).

Количество страниц зависит от объёма текста, поэтому build() делает
два прохода: черновой в память (счёт страниц) и чистовой в файл.
"""

from __future__ import annotations

import os

from astra.reports.base_builder import BasePdfBuilder
from astra.reports.natal.fonts import register_natal_fonts
from astra.reports.natal.glyphs import FONT_GLYPHS, POINT_GLYPH
from astra.reports.natal.types import NatalReportData, PlanetCard, SphereBlock
from astra.reports.natal.wheel import draw_natal_wheel
from astra.reports.theme import (
    ACCENT_BLUE,
    ACCENT_PURPLE,
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
    SQUARE_COLOR,
    TRINE_COLOR,
    TYPE,
    W,
)
from astra.reports.types import AspectData

_ELEMENT_COLORS = {
    "огонь": SQUARE_COLOR,
    "земля": TRINE_COLOR,
    "воздух": ACCENT_BLUE,
    "вода": ACCENT_PURPLE,
}

_COVER_BLOCK_H = 448.0


class NatalPdfBuilder(BasePdfBuilder):
    outline_root_title = "Натальная карта"

    def __init__(
        self,
        output_path: str,
        report: NatalReportData,
        *,
        bot_username: str | None = None,
        referral_code: str | None = None,
    ) -> None:
        super().__init__(output_path, bot_username=bot_username, referral_code=referral_code)
        self._report = report

    def _footer_right_text(self) -> str:
        return self._report.person_name

    def build(self) -> None:
        register_natal_fonts()
        sim = NatalPdfBuilder(
            os.devnull,
            self._report,
            bot_username=self._bot_username,
            referral_code=self._referral_code,
        )
        sim.total_pages = 0
        sim._build_pages()
        self.total_pages = sim.page_num
        self._build_pages()
        self.c.save()

    def _build_pages(self) -> None:
        self._page_cover()
        self._page_tldr()
        self._page_wheel()
        self._page_core_story()
        self._pack_planet_cards(self._report.personality, section="Ядро личности")
        self._pack_planet_cards(
            self._report.mind_feelings_action, section="Разум · Чувства · Действие"
        )
        self._page_balance()
        self._page_legend_and_strong_aspects()
        self._pack_aspect_pages(
            self._report.working_aspects,
            section="Фоновые аспекты",
            intro=self._report.working_aspects_intro,
        )
        self._pack_sphere_pages()
        self._pack_planet_cards(self._report.karmic, section="Кармический вектор")
        self._page_zones()
        self._page_practicum()
        self._page_conclusion()

    # --- pages ---

    def _page_cover(self) -> None:
        self._new_page("cover", "Обложка")
        self._draw_bg(vibe="cover")

        block_h = _COVER_BLOCK_H
        top = H - MARGIN - 48
        bottom = top - block_h
        self._draw_radial_glow(W / 2, H * 0.46, 150, GOLD, intensity="section")
        self._draw_card_bg(bottom, block_h, accent=GOLD, glow="section")

        cy = bottom + block_h * 0.62
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
        self.c.drawCentredString(W / 2, cy + 108, "Натальная карта")
        self.c.setFillColor(MUTED)
        self.c.setFont(FONT, TYPE["body"])
        self.c.drawCentredString(W / 2, cy + 86, "Персональный разбор")

        # аватар с инициалами
        self._draw_radial_glow(W / 2, cy + 8, 42, GOLD, intensity="card")
        self.c.setFillColor(BG_DARK)
        self.c.setStrokeColor(GOLD)
        self.c.setLineWidth(1.2)
        self.c.circle(W / 2, cy + 8, 30, fill=1, stroke=1)
        self.c.setFillColor(GOLD_LIGHT)
        self.c.setFont(FONT_BOLD, 13)
        self.c.drawCentredString(W / 2, cy + 4, self._report.person_name[:2].upper())
        self.c.setFillColor(CREAM)
        self.c.setFont(FONT, TYPE["body"])
        self.c.drawCentredString(W / 2, cy - 40, self._report.person_name)
        self.c.setFillColor(MUTED)
        self.c.setFont(FONT, TYPE["caption"])
        self.c.drawCentredString(W / 2, cy - 56, self._report.person_subtitle)

        # чипы большой тройки
        chips = self._big_three_chips()
        chip_y = bottom + 96
        chip_h = 40
        chip_w = (CONTENT_W - 40 - (len(chips) - 1) * 8) / max(len(chips), 1)
        x = MARGIN + 20
        for glyph, label, value in chips:
            self.c.setFillColor(BG_DARK)
            self.c.setStrokeColor(GOLD_DIM)
            self.c.setLineWidth(0.7)
            self.c.roundRect(x, chip_y, chip_w, chip_h, 8, fill=1, stroke=1)
            self.c.setFillColor(GOLD_LIGHT)
            self.c.setFont(FONT_GLYPHS, 11)
            self.c.drawCentredString(x + chip_w / 2, chip_y + chip_h - 16, f"{glyph} {label}")
            self.c.setFillColor(CREAM)
            self.c.setFont(FONT_BOLD, TYPE["caption"])
            self.c.drawCentredString(x + chip_w / 2, chip_y + 8, value)
            x += chip_w + 8

        read_y = bottom + 40
        self.c.setFillColor(GOLD)
        self.c.setFont(FONT, TYPE["caption"])
        label = self._report.read_time_label
        self.c.drawCentredString(W / 2, read_y, label)
        half = self.c.stringWidth(label, FONT, TYPE["caption"]) / 2
        self._draw_sparkle(W / 2 - half - 14, read_y + 4, 3, GOLD)
        self._draw_sparkle(W / 2 + half + 14, read_y + 4, 3, GOLD)

        self._draw_footer()

    def _big_three_chips(self) -> list[tuple[str, str, str]]:
        chart = self._report.chart
        chips: list[tuple[str, str, str]] = []
        sun = chart.point("Sun")
        moon = chart.point("Moon")
        if sun:
            chips.append((POINT_GLYPH["Sun"], "Солнце", sun.sign))
        if moon:
            chips.append((POINT_GLYPH["Moon"], "Луна", moon.sign))
        if chart.asc is not None:
            chips.append(("↑", "ASC", chart.asc.sign))
        return chips

    def _page_tldr(self) -> None:
        self._new_page("tldr", "Краткий итог")
        self._draw_bg(vibe="content")
        self._draw_page_header("Краткий итог", "Главное за 30 секунд")
        self._draw_radial_glow(W / 2, self._y - 40, 90, GOLD, intensity="card")

        pad = 12
        text_w = CONTENT_W - 2 * pad
        box_h = self._text_height(self._report.tldr, text_w) + 2 * pad
        bottom = self._y - box_h
        self._draw_card_bg(bottom, box_h, accent=GOLD, glow="section")
        self._draw_text_block(self._report.tldr, MARGIN + pad, self._y - pad, text_w)
        self._y = bottom - GAP["md"]

        if self._report.accuracy_note:
            note_h = self._text_height(
                self._report.accuracy_note, text_w, size=TYPE["caption"], leading=LEADING["caption"]
            ) + 2 * 10
            nb = self._y - note_h
            self._draw_card_bg(nb, note_h, accent=GOLD_DIM, glow="card")
            self._draw_text_block(
                self._report.accuracy_note, MARGIN + pad, self._y - 10, text_w,
                size=TYPE["caption"], leading=LEADING["caption"], color=MUTED,
            )
            self._y = nb - GAP["md"]

        self.c.setFillColor(GOLD_LIGHT)
        self.c.setFont(FONT_BOLD, TYPE["body"])
        self.c.drawString(MARGIN, self._y, "✦  Профиль энергии")
        self._y -= GAP["md"]

        for metric in self._report.metrics:
            self._y = self._draw_progress_bar(self._y, metric.label, metric.value, metric.color)

        self._draw_footer()

    def _page_wheel(self) -> None:
        self._new_page("wheel", "Колесо карты")
        self._draw_bg(vibe="content")
        self._draw_page_header("Колесо карты", "Небо в момент твоего рождения")

        radius = (CONTENT_W - 24) / 2
        cx = W / 2
        cy = self._y - radius - 30
        self._draw_radial_glow(cx, cy, radius * 1.15, GOLD, intensity="section")
        draw_natal_wheel(self.c, self._report.chart, cx, cy, radius)

        # мини-легенда аспектных линий под колесом
        legend_y = cy - radius - 36
        from astra.reports.theme import ASPECT_STYLES

        entries = [(k, v[0]) for k, v in ASPECT_STYLES.items() if k != "соединение"]
        entries.insert(0, ("соединение", ASPECT_STYLES["соединение"][0]))
        x = MARGIN + 6
        col_w = CONTENT_W / 3
        for i, (name, color) in enumerate(entries):
            ex = x + (i % 3) * col_w
            ey = legend_y - (i // 3) * 20
            self.c.setStrokeColor(color)
            self.c.setLineWidth(1.6)
            self.c.line(ex, ey + 3, ex + 14, ey + 3)
            self.c.setFillColor(MUTED)
            self.c.setFont(FONT, 9)
            self.c.drawString(ex + 18, ey, name)

        self._draw_planet_table(legend_y - 44)
        self._draw_footer()

    def _draw_planet_table(self, y_top: float) -> None:
        """Компактная таблица позиций: две колонки по 7 точек."""
        points = [p for p in self._report.chart.points if p.name in POINT_GLYPH]
        if not points:
            return
        half = (len(points) + 1) // 2
        col_w = (CONTENT_W - 12) / 2
        row_h = 19.0
        table_h = half * row_h + 20

        bottom = y_top - table_h
        if bottom < CONTENT_BOTTOM:
            return
        self._draw_card_bg(bottom, table_h, glow="card")

        for i, point in enumerate(points):
            col = i // half
            row = i % half
            x = MARGIN + 10 + col * (col_w + 8)
            y = y_top - 22 - row * row_h
            self.c.setFillColor(GOLD_LIGHT)
            self.c.setFont(FONT_GLYPHS, 10)
            self.c.drawString(x, y, POINT_GLYPH[point.name])
            self.c.setFillColor(MUTED)
            self.c.setFont(FONT, 9)
            self.c.drawString(x + 16, y, point.name_ru)
            value = f"{point.sign} {point.sign_deg:.0f}°"
            if point.house is not None:
                value += f" · {point.house}"
            if point.retrograde:
                value += " R"
            self.c.setFillColor(CREAM)
            self.c.setFont(FONT, 9)
            self.c.drawRightString(x + col_w - 10, y, value)

    def _page_core_story(self) -> None:
        self._new_page("story", "Портрет")
        self._draw_bg(vibe="content")
        self._draw_page_header("Портрет", "Как звучит твоя карта")
        self._draw_radial_glow(W / 2, self._y - 50, 100, GOLD, intensity="section")

        paragraphs = [p.strip() for p in self._report.core_story.split("\n\n") if p.strip()]
        pad = 14
        text_w = CONTENT_W - 2 * pad

        for idx, paragraph in enumerate(paragraphs):
            box_h = self._text_height(paragraph, text_w, leading=LEADING["body"]) + 2 * pad
            if not self._fits(box_h + GAP["sm"]) and idx > 0:
                self._draw_footer()
                self._new_page("story-cont", "Портрет (прод.)")
                self._draw_bg(vibe="content")
                self._draw_page_header("Портрет", "продолжение")

            bottom = self._y - box_h
            glow = "section" if idx == 0 else "card"
            self._draw_card_bg(bottom, box_h, accent=GOLD if idx == 0 else None, glow=glow)
            color = CREAM if idx == 0 else MUTED
            self._draw_text_block(
                paragraph, MARGIN + pad, self._y - pad, text_w,
                leading=LEADING["body"], color=color,
            )
            self._y = bottom - GAP["md"]

        self._draw_footer()

    # --- карточки планет ---

    def _planet_card_height(self, card: PlanetCard) -> float:
        pad = 12
        text_w = CONTENT_W - 2 * pad
        text_h = self._text_height(card.text, text_w, size=TYPE["body"], leading=LEADING["caption"])
        caption_h = 14 if card.caption else 0
        return 30 + caption_h + text_h + pad + 8

    def _draw_planet_card(self, y_top: float, card: PlanetCard) -> float:
        pad = 12
        text_w = CONTENT_W - 2 * pad
        h = self._planet_card_height(card)
        bottom = y_top - h
        self._draw_card_bg(bottom, h, accent=GOLD, glow="section")

        glyph = POINT_GLYPH.get(card.point_key, "✦")
        self.c.setFillColor(GOLD_LIGHT)
        self.c.setFont(FONT_GLYPHS, 15)
        self.c.drawString(MARGIN + pad, y_top - 22, glyph)
        self.c.setFillColor(CREAM)
        self.c.setFont(FONT_BOLD, TYPE["body"])
        self.c.drawString(MARGIN + pad + 22, y_top - 22, card.title)

        ty = y_top - 22
        if card.caption:
            self.c.setFillColor(GOLD)
            self.c.setFont(FONT, TYPE["caption"])
            self.c.drawString(MARGIN + pad + 22, y_top - 36, card.caption)
            ty -= 14

        self._draw_text_block(
            card.text, MARGIN + pad, ty - 18, text_w,
            size=TYPE["body"], leading=LEADING["caption"], color=MUTED,
        )
        return bottom - GAP["sm"]

    def _pack_planet_cards(self, cards: tuple[PlanetCard, ...], *, section: str) -> None:
        if not cards:
            return
        idx = 0
        page_no = 0
        while idx < len(cards):
            self._new_page(
                f"{section}-{page_no}", section if page_no == 0 else f"{section} (прод.)"
            )
            self._draw_bg(vibe="content")
            self._draw_page_header(section, "продолжение" if page_no else "")
            placed = 0
            while idx < len(cards):
                h = self._planet_card_height(cards[idx])
                gap = GAP["sm"] if placed else 0
                if placed > 0 and not self._fits(h + gap):
                    break
                self._y -= gap
                self._y = self._draw_planet_card(self._y, cards[idx])
                idx += 1
                placed += 1
            self._draw_footer()
            page_no += 1

    def _page_balance(self) -> None:
        chart = self._report.chart
        if not chart.element_balance:
            return
        self._new_page("balance", "Стихии и кресты")
        self._draw_bg(vibe="content")
        self._draw_page_header("Стихии и кресты", "Баланс энергий карты")

        total = sum(chart.element_balance.values()) or 1.0
        self.c.setFillColor(GOLD_LIGHT)
        self.c.setFont(FONT_BOLD, TYPE["body"])
        self.c.drawString(MARGIN, self._y, "✦  Стихии")
        self._y -= GAP["md"]
        for element in ("огонь", "земля", "воздух", "вода"):
            value = chart.element_balance.get(element, 0.0)
            color = _ELEMENT_COLORS[element]
            self._y = self._draw_progress_bar(self._y, element.capitalize(), value / total, color)

        self._y -= GAP["xs"]
        self.c.setFillColor(GOLD_LIGHT)
        self.c.setFont(FONT_BOLD, TYPE["body"])
        self.c.drawString(MARGIN, self._y, "✦  Кресты")
        self._y -= GAP["md"]
        mod_total = sum(chart.modality_balance.values()) or 1.0
        for modality in ("кардинальный", "фиксированный", "мутабельный"):
            value = chart.modality_balance.get(modality, 0.0)
            self._y = self._draw_progress_bar(
                self._y, modality.capitalize(), value / mod_total, GOLD
            )

        if self._report.balance_note:
            pad = 12
            text_w = CONTENT_W - 2 * pad
            note_h = self._text_height(
                self._report.balance_note, text_w, size=TYPE["caption"], leading=LEADING["caption"]
            ) + 2 * pad
            if self._fits(note_h):
                bottom = self._y - note_h
                self._draw_card_bg(bottom, note_h, accent=GOLD_DIM, glow="card")
                self._draw_text_block(
                    self._report.balance_note, MARGIN + pad, self._y - pad, text_w,
                    size=TYPE["caption"], leading=LEADING["caption"], color=MUTED,
                )
                self._y = bottom

        self._draw_footer()

    def _page_legend_and_strong_aspects(self) -> None:
        aspects = self._report.strong_aspects
        if not aspects:
            return
        self._new_page("strong", "Ключевые аспекты")
        self._draw_bg(vibe="content")
        self._draw_page_header("Ключевые аспекты", "Орб < 2° — работают постоянно")

        self._y = self._draw_legend(self._y)
        self._y = self._draw_aspect_card(self._y, aspects[0], hot=True)

        idx = 1
        while idx < len(aspects):
            h = self._aspect_card_height(aspects[idx], hot=True) + GAP["sm"]
            if not self._fits(h):
                break
            self._y = self._draw_aspect_card(self._y, aspects[idx], hot=True)
            idx += 1

        self._draw_footer()
        if idx < len(aspects):
            self._pack_aspect_pages(aspects[idx:], section="Ключевые аспекты", hot=True)

    def _pack_aspect_pages(
        self,
        aspects: tuple[AspectData, ...],
        *,
        section: str,
        hot: bool = False,
        intro: str = "",
    ) -> None:
        if not aspects:
            return
        idx = 0
        page_no = 0
        while idx < len(aspects):
            subtitle = intro if page_no == 0 and intro else ("продолжение" if page_no else "")
            self._new_page(
                f"{section}-{page_no}", section if page_no == 0 else f"{section} (прод.)"
            )
            self._draw_bg(vibe="content")
            self._draw_page_header(section, subtitle)
            placed = 0
            while idx < len(aspects):
                h = self._aspect_card_height(aspects[idx], hot=hot)
                gap = GAP["sm"] if placed else 0
                if placed > 0 and not self._fits(h + gap):
                    break
                self._y -= gap
                self._y = self._draw_aspect_card(self._y, aspects[idx], hot=hot)
                idx += 1
                placed += 1
            self._draw_footer()
            page_no += 1

    # --- сферы жизни ---

    def _sphere_height(self, sphere: SphereBlock) -> float:
        pad = 12
        text_w = CONTENT_W - 2 * pad
        text_h = self._text_height(sphere.text, text_w, size=TYPE["body"], leading=LEADING["caption"])
        tip_h = self._text_height(sphere.tip, text_w - 8, size=TYPE["caption"], leading=LEADING["caption"])
        return 30 + 14 + text_h + 8 + tip_h + 18 + pad

    def _draw_sphere(self, y_top: float, sphere: SphereBlock) -> float:
        pad = 12
        text_w = CONTENT_W - 2 * pad
        h = self._sphere_height(sphere)
        bottom = y_top - h
        self._draw_card_bg(bottom, h, accent=GOLD, glow="section")

        self.c.setFillColor(GOLD_LIGHT)
        self.c.setFont(FONT_BOLD, TYPE["body"])
        self.c.drawString(MARGIN + pad, y_top - 20, sphere.title)
        self.c.setFillColor(GOLD)
        self.c.setFont(FONT, TYPE["caption"])
        self.c.drawString(MARGIN + pad, y_top - 34, sphere.factors)

        ty = self._draw_text_block(
            sphere.text, MARGIN + pad, y_top - 52, text_w,
            size=TYPE["body"], leading=LEADING["caption"], color=CREAM,
        )

        self.c.setFillColor(GOLD)
        self.c.setFont(FONT_BOLD, TYPE["caption"])
        self.c.drawString(MARGIN + pad, ty - 8, "→")
        self._draw_text_block(
            sphere.tip, MARGIN + pad + 14, ty - 8, text_w - 14,
            size=TYPE["caption"], leading=LEADING["caption"], color=MUTED,
        )
        return bottom - GAP["sm"]

    def _pack_sphere_pages(self) -> None:
        spheres = self._report.spheres
        if not spheres:
            return
        idx = 0
        page_no = 0
        while idx < len(spheres):
            self._new_page(
                f"spheres-{page_no}", "Сферы жизни" if page_no == 0 else "Сферы жизни (прод.)"
            )
            self._draw_bg(vibe="content")
            self._draw_page_header("Сферы жизни", "продолжение" if page_no else "Куда направлена энергия карты")
            placed = 0
            while idx < len(spheres):
                h = self._sphere_height(spheres[idx])
                gap = GAP["sm"] if placed else 0
                if placed > 0 and not self._fits(h + gap):
                    break
                self._y -= gap
                self._y = self._draw_sphere(self._y, spheres[idx])
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

    def _page_practicum(self) -> None:
        tips = self._report.practical_tips
        if not tips:
            return
        self._new_page("practicum", "Практикум")
        self._draw_bg(vibe="content")
        self._draw_page_header("Практикум", "Конкретные шаги на неделю")

        pad = 14
        text_w = CONTENT_W - 2 * pad - 26
        for i, tip in enumerate(tips, start=1):
            tip_h = self._text_height(tip, text_w, size=TYPE["body"], leading=LEADING["body"]) + 2 * pad
            if not self._fits(tip_h + GAP["sm"]):
                break
            bottom = self._y - tip_h
            self._draw_card_bg(bottom, tip_h, accent=GOLD, glow="card")
            self.c.setFillColor(GOLD)
            self.c.setFont(FONT_BOLD, TYPE["h2"])
            self.c.drawString(MARGIN + pad, self._y - pad - 4, str(i))
            self._draw_text_block(
                tip, MARGIN + pad + 26, self._y - pad, text_w,
                size=TYPE["body"], leading=LEADING["body"], color=CREAM,
            )
            self._y = bottom - GAP["sm"]

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
        quote_h = self._text_height(quote, inner_w, size=TYPE["quote"], leading=LEADING["body"] + 2)
        card_h = pad + quote_h + GAP["lg"] + tip_label_h + tip_body_h + pad

        title_y = H - MARGIN - 22
        self._draw_sparkle(MARGIN + 8, title_y - 4, 4)
        self._draw_sparkle(W - MARGIN - 8, title_y - 4, 4)
        self.c.setFillColor(GOLD_LIGHT)
        self.c.setFont(FONT_BOLD, TYPE["h1"])
        self.c.drawCentredString(W / 2, title_y, "ВЫВОД")
        self.c.setFillColor(MUTED)
        self.c.setFont(FONT, TYPE["caption"])
        self.c.drawCentredString(W / 2, title_y - 18, "главная мысль твоей карты")
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
            quote, card_x + pad, qy - 8, inner_w,
            size=TYPE["quote"], leading=LEADING["body"] + 2, color=CREAM,
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
            tip, card_x + pad + 4, tip_box_top - 38, inner_w - 8,
            size=TYPE["body"], color=CREAM,
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


def generate_natal_pdf(
    output_path: str,
    report: NatalReportData,
    *,
    bot_username: str | None = None,
    referral_code: str | None = None,
) -> None:
    NatalPdfBuilder(
        output_path,
        report,
        bot_username=bot_username,
        referral_code=referral_code,
    ).build()
