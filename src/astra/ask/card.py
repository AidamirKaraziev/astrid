"""Карточка с числом: картинка, которую пересылают друзьям.

Формат сторис (1080×1350), тёмный фон в тон боту, крупное число по центру.
Личных данных на карточке нет намеренно — ни имени, ни даты рождения: её
показывают подругам, и она не должна выдавать чужой профиль.

Рендерим Pillow'ом и локально: карточка уходит человеку сразу после оплаты,
не дожидаясь разбора от LLM, — это и закрывает паузу ожидания.
"""

from __future__ import annotations

import random
from io import BytesIO
from pathlib import Path

from astra.ask.schemas import ChildrenResult, FatedPartnersResult

WIDTH = 1080
HEIGHT = 1350

_FONT_PATH = Path(__file__).resolve().parents[1] / "reports" / "natal" / "assets" / "fonts" / "DejaVuSans.ttf"

_BG_TOP = (16, 20, 42)
_BG_BOTTOM = (30, 16, 54)
_ACCENT = (233, 213, 255)
_TEXT = (246, 244, 255)
_MUTED = (168, 162, 198)


def _plural(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "судьбоносный\nпартнёр"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return "судьбоносных\nпартнёра"
    return "судьбоносных\nпартнёров"


def _background(image_module, draw_module) -> "object":
    image = image_module.new("RGB", (WIDTH, HEIGHT), _BG_TOP)
    draw = draw_module.Draw(image)
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        draw.line(
            [(0, y), (WIDTH, y)],
            fill=tuple(
                round(top + (bottom - top) * ratio)
                for top, bottom in zip(_BG_TOP, _BG_BOTTOM, strict=True)
            ),
        )
    # Звёздная пыль: фиксированный seed — карточка всегда выглядит одинаково.
    rng = random.Random(20260728)
    for _ in range(160):
        x, y = rng.randrange(WIDTH), rng.randrange(HEIGHT)
        radius = rng.choice((1, 1, 2))
        shade = rng.randrange(90, 190)
        draw.ellipse((x, y, x + radius, y + radius), fill=(shade, shade, min(255, shade + 40)))
    return image


def render_card(*, hero: str, label: str, footnote: str) -> bytes:
    """Общая карточка раздела: крупное главное, подпись, строка снизу."""
    from PIL import Image, ImageDraw, ImageFont

    image = _background(Image, ImageDraw)
    draw = ImageDraw.Draw(image)

    # Длинный герой (период «2029–2030») не влезает кеглем числа — ужимаем.
    hero_size = 400 if len(hero) <= 2 else 190
    font_hero = ImageFont.truetype(str(_FONT_PATH), hero_size)
    font_label = ImageFont.truetype(str(_FONT_PATH), 62)
    font_footnote = ImageFont.truetype(str(_FONT_PATH), 44)
    font_footer = ImageFont.truetype(str(_FONT_PATH), 34)

    hero_y = 300 if hero_size == 400 else 430
    _centered(draw, hero, y=hero_y, font=font_hero, fill=_ACCENT)
    _centered(draw, label, y=790, font=font_label, fill=_TEXT, spacing=16)

    draw.line([(340, 1010), (740, 1010)], fill=_MUTED, width=2)
    _centered(draw, footnote, y=1050, font=font_footnote, fill=_MUTED)
    _centered(draw, "по натальной карте · Астрид", y=1230, font=font_footer, fill=_MUTED)

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def render_fated_partners_card(result: FatedPartnersResult) -> bytes:
    """PNG с числом судьбоносных партнёров."""
    return render_card(
        hero=str(result.total),
        label=_plural(result.total),
        footnote=f"уже было {result.past}   ·   впереди {result.future}",
    )


def render_children_card(result: ChildrenResult) -> bytes:
    """PNG с лучшим окном темы детей: годы крупно."""
    from astra.llm.prompts.ask.children import count_words, window_period

    if result.best_window is None:
        return render_card(
            hero="✨",
            label="тема детей\nв твоей карте",
            footnote=f"карта показывает {count_words(result.count_hint)}",
        )
    return render_card(
        hero=window_period(result.best_window),
        label="лучшее окно\nдля темы детей",
        footnote=f"карта показывает {count_words(result.count_hint)}",
    )


def _centered(draw, text: str, *, y: int, font, fill, spacing: int = 8) -> None:
    draw.multiline_text(
        (WIDTH // 2, y),
        text,
        font=font,
        fill=fill,
        anchor="ma",
        align="center",
        spacing=spacing,
    )
