"""Кнопки под сообщением рассылки.

Два вида: переход в раздел бота и обычная ссылка. Разделы заданы списком, а не
свободным вводом, — иначе кнопка приведёт в никуда, и это выяснится уже после
отправки тысяче человек.
"""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from astra.telegram.button_texts import (
    CB_ASK_HOME,
    CB_DAY_CARD_FORECAST,
    CB_TAROT_SECTION,
    CB_WHEEL_HOME,
)
from astra.broadcasts.sections import SECTION_TITLES
from astra.telegram.keyboards import CB_TAROT_DAILY

# Ключ раздела → callback существующего экрана. Подписи живут в sections.py,
# который панель импортирует без aiogram.
CALLBACKS: dict[str, str] = {
    "tarot": CB_TAROT_SECTION,
    "tarot_daily": CB_TAROT_DAILY,
    "day_card": CB_DAY_CARD_FORECAST,
    "ask": CB_ASK_HOME,
    "wheel": CB_WHEEL_HOME,
}


def broadcast_keyboard(buttons: list[dict[str, Any]] | None) -> InlineKeyboardMarkup | None:
    """Клавиатура из описаний кнопок; None — кнопок нет."""
    if not buttons:
        return None

    rows: list[list[InlineKeyboardButton]] = []
    for button in buttons:
        title = (button.get("title") or "").strip()
        section = button.get("section")
        url = (button.get("url") or "").strip()

        if section and section in CALLBACKS:
            default_title = SECTION_TITLES.get(section, "Открыть")
            rows.append(
                [InlineKeyboardButton(text=title or default_title, callback_data=CALLBACKS[section])],
            )
        elif url.startswith(("http://", "https://", "tg://")) and title:
            rows.append([InlineKeyboardButton(text=title, url=url)])

    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
