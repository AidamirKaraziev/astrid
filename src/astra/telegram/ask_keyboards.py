"""Клавиатуры покупки и выдачи ответа в разделе «Спроси Астрид»."""

from __future__ import annotations

from urllib.parse import quote

from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from astra.ask.models import AskReading
from astra.core.config import get_settings
from astra.telegram.button_texts import (
    CB_ASK_ARCHIVE_PREFIX,
    CB_ASK_REDO_PREFIX,
    CB_ASK_CALIB_PREFIX,
    CB_ASK_COMPAT_CROSSSELL,
    CB_ASK_GATE_SKIP,
    CB_ASK_GATE_TIME,
    CB_ASK_HOME,
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


def ask_status_keyboard(product) -> InlineKeyboardMarkup:  # noqa: ANN001 — AskProduct, циклический импорт
    """Калибрующий вопрос продукта: подписи свои у каждого вопроса."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=product.calibration_yes,
                    callback_data=f"{CB_ASK_CALIB_PREFIX}{product.key}:yes",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=product.calibration_no,
                    callback_data=f"{CB_ASK_CALIB_PREFIX}{product.key}:no",
                ),
            ],
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
                text="🔁 Сделать разбор заново",
                callback_data=f"{CB_ASK_REDO_PREFIX}{reading.question_key}",
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
    from astra.telegram.ask_text import ASK_QUESTION_TOPIC

    topic = ASK_QUESTION_TOPIC.get(reading.question_key)
    if topic:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔙 Другие вопросы",
                    callback_data=f"{CB_ASK_TOPIC_PREFIX}{topic}",
                ),
            ],
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ask_archive_keyboard(question_key: str) -> InlineKeyboardMarkup:
    """У человека уже есть купленный ответ — показываем его бесплатно."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📖 Показать мой ответ",
                    callback_data=f"{CB_ASK_ARCHIVE_PREFIX}{question_key}",
                    style=ButtonStyle.PRIMARY,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔁 Сделать разбор заново",
                    callback_data=f"{CB_ASK_REDO_PREFIX}{question_key}",
                ),
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=CB_ASK_HOME)],
        ],
    )
