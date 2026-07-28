"""Раздел «Спроси Астрид»: готовые вопросы к своей карте.

Сейчас реализован только верхний уровень — список тем. Нажатие на тему и на
«свой вопрос» честно говорит, что вопросы внутри ещё готовятся: экран уже
живой, но ничего не обещает лишнего.

Навигация инлайновая (callback), а не Reply-кнопками: следующий уровень —
вопросы и оплата — ляжет тем же механизмом, без коллизий со свободным текстом.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from astra.telegram import ask_text as A
from astra.telegram.button_texts import (
    BTN_ASK_ASTRID,
    CB_ASK_CLOSE,
    CB_ASK_HOME,
    CB_ASK_OWN,
    CB_ASK_TOPIC_PREFIX,
)
from astra.telegram.keyboards import ask_astrid_keyboard, ask_topic_keyboard

router = Router(name="ask_astrid")


async def open_ask_hub(message: Message) -> None:
    """Открыть раздел новым сообщением (из кнопки меню)."""
    await message.answer(A.ASK_HUB_TEXT, reply_markup=ask_astrid_keyboard())


async def _edit_or_answer(
    callback: CallbackQuery,
    text: str,
    markup: InlineKeyboardMarkup,
) -> None:
    """Правим текущее сообщение; если нельзя (фото/уже изменено) — шлём новое."""
    msg = callback.message
    if not isinstance(msg, Message):
        return
    try:
        await msg.edit_text(text, reply_markup=markup)
    except Exception:
        await msg.answer(text, reply_markup=markup)


@router.message(F.text == BTN_ASK_ASTRID)
async def ask_astrid_button(message: Message, state: FSMContext) -> None:
    """Кнопка меню вне активного сценария (в FSM её ловит navigation)."""
    await state.clear()
    await open_ask_hub(message)


@router.callback_query(F.data == CB_ASK_HOME)
async def cb_ask_home(callback: CallbackQuery) -> None:
    await callback.answer()
    await _edit_or_answer(callback, A.ASK_HUB_TEXT, ask_astrid_keyboard())


@router.callback_query(F.data.startswith(CB_ASK_TOPIC_PREFIX))
async def cb_ask_topic(callback: CallbackQuery) -> None:
    await callback.answer()
    key = (callback.data or "").removeprefix(CB_ASK_TOPIC_PREFIX)
    label = A.ASK_TOPIC_LABELS.get(key)
    if label is None:
        return
    text = A.ASK_TOPIC_SOON_TEXT.format(label=f"<b>{label}</b>")
    await _edit_or_answer(callback, text, ask_topic_keyboard())


@router.callback_query(F.data == CB_ASK_OWN)
async def cb_ask_own(callback: CallbackQuery) -> None:
    await callback.answer()
    await _edit_or_answer(callback, A.ASK_OWN_SOON_TEXT, ask_topic_keyboard())


@router.callback_query(F.data == CB_ASK_CLOSE)
async def cb_ask_close(callback: CallbackQuery) -> None:
    await callback.answer()
    msg = callback.message
    if isinstance(msg, Message):
        try:
            await msg.delete()
        except Exception:
            pass
