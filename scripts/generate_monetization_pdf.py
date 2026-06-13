#!/usr/bin/env python3
"""Generate PDF portfolio doc for Astra monetization (colleague review)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "monetization" / "Astra-портфель-монетизации-2026-06-13.pdf"
FONT = Path("/Library/Fonts/Arial Unicode.ttf")


class PortfolioPDF(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("ArialUni", size=8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"Astra · Портфель монетизации · {date.today():%d.%m.%Y} · стр. {self.page_no()}", align="C")


def _font(pdf: FPDF, size: int = 10, bold: bool = False) -> None:
    style = "B" if bold else ""
    pdf.set_font("ArialUni", style=style, size=size)
    pdf.set_text_color(20, 20, 20)


def section(pdf: PortfolioPDF, title: str) -> None:
    pdf.ln(4)
    _font(pdf, 12, bold=True)
    pdf.multi_cell(0, 7, title)
    pdf.ln(1)


def body(pdf: PortfolioPDF, text: str) -> None:
    _font(pdf, 10)
    pdf.multi_cell(0, 5, text)
    pdf.ln(1)


def table(
    pdf: PortfolioPDF,
    headers: list[str],
    rows: list[list[str]],
    widths: list[float],
    font_size: int = 7,
) -> None:
    _font(pdf, font_size, bold=True)
    pdf.set_fill_color(240, 240, 245)
    for i, h in enumerate(headers):
        pdf.cell(widths[i], 6, h, border=1, fill=True, align="C")
    pdf.ln()

    _font(pdf, font_size)
    for row in rows:
        x0, y0 = pdf.get_x(), pdf.get_y()
        line_h = 5
        heights: list[float] = []
        lines_per_cell: list[list[str]] = []
        for i, cell in enumerate(row):
            pdf.set_xy(x0 + sum(widths[:i]), y0)
            lines = pdf.multi_cell(widths[i], line_h, cell, border=0, split_only=True)
            lines_per_cell.append(lines)
            heights.append(len(lines) * line_h)
        row_h = max(heights) if heights else line_h

        if y0 + row_h > pdf.h - 20:
            pdf.add_page()
            y0 = pdf.get_y()

        for i, cell in enumerate(row):
            x = x0 + sum(widths[:i])
            pdf.rect(x, y0, widths[i], row_h)
            pdf.set_xy(x + 0.5, y0 + 0.5)
            pdf.multi_cell(widths[i] - 1, line_h, cell, border=0)
        pdf.set_xy(x0, y0 + row_h)


def build() -> Path:
    OUT.parent.mkdir(parents=True, exist_ok=True)

    pdf = PortfolioPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("ArialUni", "", str(FONT))
    pdf.add_font("ArialUni", "B", str(FONT))

    # Title
    pdf.add_page()
    _font(pdf, 22, bold=True)
    pdf.cell(0, 14, "Astra — портфель монетизации", ln=True)
    _font(pdf, 12)
    pdf.cell(0, 8, "Telegram-бот · персональные предсказания · RU-аудитория", ln=True)
    _font(pdf, 10)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 6, f"Дата: {date.today():%d.%m.%Y} · Версия: черновик для обсуждения", ln=True)
    pdf.ln(6)

    body(
        pdf,
        "Документ для детального разбора с коллегой. Содержит утверждённый продуктовый "
        "портфель, оценки по 5 метрикам (шкала 1–5), ценовые ориентиры и открытые вопросы.",
    )

    section(pdf, "Контекст")
    table(
        pdf,
        ["Параметр", "Значение"],
        [
            ["Продукт", "Telegram-бот Astra — ежедневные персональные предсказания"],
            ["ЦА", "Женщины RU, «магическое мышление»; совместимость, будущее"],
            ["MVP", "Бесплатно; баллы за визиты и рефералов"],
            ["Ограничения", "Solo-dev; сервер deadtiger (CPU-only LLM ≤4B)"],
            ["Цель", "~100k платящих x 100 руб. ~ 10 млн руб./мес"],
        ],
        [55, 222],
        font_size=9,
    )

    section(pdf, "Шкала оценок (1–5)")
    table(
        pdf,
        ["Метрика", "1", "5"],
        [
            ["Сложность", "быстро", "месяцы, новый стек"],
            ["ЦА", "мимо аудитории", "прямое попадание"],
            ["Монетизация", "сложно продать", "импульс / подписка"],
            ["Популярность", "ниша", "массовый запрос RU"],
            ["Спрос", "nice to have", "«хочу прямо сейчас»"],
        ],
        [45, 116, 116],
        font_size=9,
    )
    body(pdf, "Приоритет = (ЦА + Монет + Спрос + Попул) - Сложность. Цена в руб., ориентир.")

    section(pdf, "[ПЛАТНО] Подписка и разборы")
    paid_core = [
        ["1", "Premium-подписка", "3", "4", "5", "5", "4", "199-399/мес"],
        ["6", "Натал (краткий)", "4", "5", "4", "5", "5", "349-599"],
        ["7", "Натал (полный)", "5", "5", "4", "4", "4", "799-1499"],
        ["8", "Совместимость пары", "4", "5", "5", "5", "5", "499-999"],
        ["9", "Совместимость «я+он/она»", "3", "5", "5", "5", "5", "349-799"],
        ["10", "Прогноз на месяц", "3", "4", "4", "4", "4", "249-499"],
        ["11", "Прогноз на год", "3", "4", "4", "4", "3", "599-999"],
        ["12", "Разбор транзита", "2", "3", "3", "3", "3", "149-349"],
        ["13", "Карьерный разбор", "3", "3", "3", "3", "3", "299-599"],
        ["14", "Любовный разбор", "3", "5", "5", "5", "5", "349-699"],
        ["15", "«Вопрос дня»", "2", "4", "5", "4", "4", "99-199"],
    ]
    w = [8, 52, 12, 10, 12, 12, 12, 28]
    table(
        pdf,
        ["#", "Продукт", "Сл.", "ЦА", "Мон.", "Поп.", "Сп.", "Цена"],
        paid_core,
        w,
    )

    section(pdf, "[ПЛАТНО] Таро, нумерология, видео")
    table(
        pdf,
        ["#", "Продукт", "Сл.", "ЦА", "Мон.", "Поп.", "Сп.", "Цена"],
        [
            ["16", "Таро: 3 карты", "3", "4", "4", "5", "5", "149-299"],
            ["17", "Таро: отношения", "3", "5", "5", "5", "5", "199-399"],
            ["18", "Таро: решение", "3", "4", "4", "4", "4", "149-299"],
            ["19", "Карта дня Premium", "2", "4", "3", "3", "3", "99-149"],
            ["20", "Нумерология", "3", "4", "4", "4", "4", "199-399"],
            ["41", "Видео совместимости*", "5", "5", "5", "5", "5", "699-1999"],
        ],
        w,
    )
    body(pdf, "* #41 в портфеле, но не v1: рендер видео не на deadtiger (облако/Mac).")

    section(pdf, "[ПЛАТНО] Механики баллов")
    table(
        pdf,
        ["#", "Механика", "Сл.", "ЦА", "Мон.", "Поп.", "Сп."],
        [
            ["26", "Оплата баллами", "3", "4", "4", "4", "4"],
            ["27", "Баллы + доплата", "3", "4", "5", "4", "4"],
            ["28", "Реферальный бонус", "2", "4", "3", "4", "4"],
            ["29", "Streak-награды", "2", "4", "2", "4", "3"],
            ["30", "Лутбокс", "3", "3", "3", "3", "2"],
        ],
        [8, 52, 12, 10, 12, 12, 12],
    )

    section(pdf, "[БЕСПЛАТНО / ГИПОТЕЗЫ / ИССЛЕДОВАНИЕ]")
    table(
        pdf,
        ["Статус", "#", "Продукт", "Сл.", "ЦА", "Мон.", "Цена", "Комментарий"],
        [
            ["Бесплатно", "35", "PDF-книга года", "4", "5", "2*", "0", "Retention, upsell"],
            ["Гипотеза", "37", "Аудио TTS Astrid", "4", "4", "3", "+49-99", "Spike RU TTS"],
            ["Гипотеза", "41", "Видео совместимости", "5", "5", "5", "699-1999", "Viral, share"],
            ["Исслед.", "39", "Affiliate", "2", "3", "4", "5-15%", "Admitad, UX"],
            ["Исслед.", "40", "White-label", "5", "2", "4", "rev.share", "B2B блогеры"],
        ],
        [22, 8, 48, 10, 10, 12, 22, 68],
        font_size=7,
    )

    section(pdf, "[ПОД ВОПРОСОМ] 9 позиций")
    table(
        pdf,
        ["#", "Продукт", "Сл.", "ЦА", "Мон.", "Сп.", "Цена", "Плюсы / минусы"],
        [
            ["21", "Пакет «Старт»", "3", "5", "4", "4", "899-1299", "↑ чек / прайсинг"],
            ["22", "Пакет «Отношения»", "3", "5", "5", "5", "999-1499", "core ЦА / нужны базовые"],
            ["23", "Пакет «Год вперёд»", "4", "4", "4", "3", "1499-2499", "LTV / апдейты"],
            ["24", "Семейный пакет", "4", "4", "4", "3", "499-799/мес", "ARPU / UX профилей"],
            ["25", "B2B wellness", "5", "2", "3", "2", "50k+", "чеки / не core"],
            ["31", "Живой астролог", "4", "5", "5", "4", "1500-5000", "маржа / supply"],
            ["32", "Second opinion", "5", "4", "4", "3", "999-1999", "дифф. / SLA"],
            ["33", "Групповой эфир", "4", "4", "3", "3", "299-999", "масштаб / аудитория"],
            ["34", "Куратор неделя", "5", "4", "4", "2", "2999+", "premium / не масштаб"],
        ],
        [8, 38, 10, 10, 12, 10, 24, 88],
        font_size=7,
    )

    section(pdf, "Приоритет запуска v1")
    table(
        pdf,
        ["Ранг", "#", "Продукт", "Балл", "Примечание"],
        [
            ["1", "9", "Совместимость «я + он/она»", "17", "Лучший первый платный"],
            ["1", "14", "Любовный разбор", "17", "Core ЦА"],
            ["1", "17", "Таро: отношения", "17", "Core ЦА"],
            ["4", "8", "Совместимость пары", "16", ""],
            ["4", "15", "«Вопрос дня»", "16", "Микро-транзакция 99 руб."],
            ["4", "41", "Видео совместимости", "16", "Не v1 — сложность"],
            ["7", "16", "Таро: 3 карты", "15", ""],
        ],
        [14, 8, 58, 14, 82],
        font_size=9,
    )
    body(pdf, "Рекомендуемая очередь: 15 → 9 → 14 → 17 → 16 → 1 (подписка) → 26/27 (баллы).")

    section(pdf, "Вопросы для обсуждения")
    questions = [
        "1. Адекватны ли ценовые диапазоны для RU Telegram?",
        "2. Пакеты 21–23 — включать в v1 или ждать отдельных продуктов?",
        "3. Видео #41 — premium сразу или freemium-тизер (15 сек)?",
        "4. Экономика баллов: какой % чека покрывать баллами без убытка?",
        "5. Affiliate / white-label — откладываем до 200k руб./мес или раньше?",
    ]
    for q in questions:
        body(pdf, q)

    pdf.output(str(OUT))
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"PDF: {path}")
