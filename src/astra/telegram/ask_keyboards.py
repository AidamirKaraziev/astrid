"""Клавиатуры покупки и выдачи ответа в разделе «Спроси Астрид»."""

from __future__ import annotations

from urllib.parse import quote

from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from astra.ask.models import AskReading
from astra.core.config import get_settings
from astra.telegram.button_texts import (
    CB_ASK_ANSWER_ARCHIVE,
    CB_ASK_COMPAT_CROSSSELL,
    CB_ASK_GATE_SKIP,
    CB_ASK_GATE_TIME,
    CB_ASK_HOME,
    CB_ASK_STATUS_FREE,
    CB_ASK_STATUS_TAKEN,
    CB_ASK_TOPIC_PREFIX,
)

_SHARE_TEXT = "Узнала по своей натальной карте ✨ Проверь свою"


def ask_gate_keyboard() -> InlineKeyboardMarkup:
    """Нет времени рождения: предлагаем вписать, но не запираем."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🕐 Вписать время рождения",
                    callback_data=CB_ASK_GATE_TIME,
                    style=ButtonStyle.PRIMARY,
                ),
            ],
            [InlineKeyboardButton(text="Ответить без времени", callback_data=CB_ASK_GATE_SKIP)],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=CB_ASK_HOME)],
        ],
    )


def ask_status_keyboard() -> InlineKeyboardMarkup:
    """Один вопрос перед ответом — он калибрует расчёт."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сейчас в отношениях", callback_data=CB_ASK_STATUS_TAKEN)],
            [InlineKeyboardButton(text="Сейчас свободна/свободен", callback_data=CB_ASK_STATUS_FREE)],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=CB_ASK_HOME)],
        ],
    )


def ask_answer_keyboard(reading: AskReading, *, referral_code: str | None) -> InlineKeyboardMarkup:
    """Под разбором: поделиться, кросс-продажа, возврат к вопросам."""
    rows: list[list[InlineKeyboardButton]] = []
    if referral_code:
        bot_username = get_settings().telegram_bot_username.lstrip("@")
        link = f"https://t.me/{bot_username}?start=ref_{referral_code}"
        rows.append(
            [
                InlineKeyboardButton(
                    text="💫 Поделиться",
                    url=f"https://t.me/share/url?url={link}&text={quote(_SHARE_TEXT)}",
                ),
            ],
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="💕 А что чувствует конкретный человек",
                callback_data=CB_ASK_COMPAT_CROSSSELL,
            ),
        ],
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 Другие вопросы",
                callback_data=f"{CB_ASK_TOPIC_PREFIX}love",
            ),
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ask_archive_keyboard() -> InlineKeyboardMarkup:
    """У человека уже есть купленный ответ — показываем его бесплатно."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📖 Показать мой ответ",
                    callback_data=CB_ASK_ANSWER_ARCHIVE,
                    style=ButtonStyle.PRIMARY,
                ),
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=CB_ASK_HOME)],
        ],
    )
