"""Служба заботы: хаб помощи и FAQ-самопомощь.

Вход — кнопка «💬 Помощь» в меню, команды /help и /paysupport, а также
контекстная подсказка «Нужна помощь?» в точках сбоя. Дальше — готовые ответы
по темам; если не помогло, кнопка ведёт к живому оператору (релей — в
support_relay.py).
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from astra.core.config import Settings, get_settings
from astra.telegram import support_text as T
from astra.telegram.button_texts import (
    BTN_HELP,
    CB_SUPPORT_CLOSE,
    CB_SUPPORT_FAQ_PREFIX,
    CB_SUPPORT_HUB,
    CB_SUPPORT_WRITE,
)
from astra.telegram.keyboards import (
    support_faq_keyboard,
    support_hub_keyboard,
    support_writing_keyboard,
)
from astra.telegram.states import SupportStates

router = Router(name="support")


def _relay_enabled(settings: Settings) -> bool:
    return settings.telegram_admin_group_id != 0


def can_reach_human(settings: Settings) -> bool:
    """Есть ли вообще способ достучаться до человека: релей или личный аккаунт."""
    return _relay_enabled(settings) or bool(settings.telegram_support_username.strip())


async def open_support_hub(message: Message) -> None:
    """Открыть хаб помощи новым сообщением (из кнопки/команды)."""
    settings = get_settings()
    await message.answer(
        T.SUPPORT_HUB_TEXT,
        reply_markup=support_hub_keyboard(can_reach_human(settings)),
    )


@router.message(F.text == BTN_HELP)
async def support_button(message: Message, state: FSMContext) -> None:
    """Кнопка «💬 Помощь» вне активного сценария (в FSM её ловит navigation)."""
    await state.clear()
    await open_support_hub(message)


async def _show_hub_inline(callback: CallbackQuery) -> None:
    """Показать хаб в ответ на callback: правим текущее сообщение, иначе — новым."""
    settings = get_settings()
    markup = support_hub_keyboard(can_reach_human(settings))
    msg = callback.message
    if not isinstance(msg, Message):
        return
    try:
        await msg.edit_text(T.SUPPORT_HUB_TEXT, reply_markup=markup)
    except Exception:
        # Сообщение с фото/подписью или уже изменено — просто шлём новое.
        await msg.answer(T.SUPPORT_HUB_TEXT, reply_markup=markup)


@router.callback_query(F.data == CB_SUPPORT_HUB)
async def cb_hub(callback: CallbackQuery) -> None:
    await callback.answer()
    await _show_hub_inline(callback)


@router.callback_query(F.data.startswith(CB_SUPPORT_FAQ_PREFIX))
async def cb_faq(callback: CallbackQuery) -> None:
    await callback.answer()
    key = (callback.data or "").removeprefix(CB_SUPPORT_FAQ_PREFIX)
    answer = T.FAQ_ANSWERS.get(key)
    msg = callback.message
    if answer is None or not isinstance(msg, Message):
        return
    settings = get_settings()
    try:
        await msg.edit_text(answer, reply_markup=support_faq_keyboard(can_reach_human(settings)))
    except Exception:
        await msg.answer(answer, reply_markup=support_faq_keyboard(can_reach_human(settings)))


@router.callback_query(F.data == CB_SUPPORT_WRITE)
async def cb_write(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    settings = get_settings()
    msg = callback.message
    if not isinstance(msg, Message):
        return

    if _relay_enabled(settings):
        await state.set_state(SupportStates.writing)
        await msg.answer(T.SUPPORT_WRITE_PROMPT, reply_markup=support_writing_keyboard())
        return

    username = settings.telegram_support_username.strip().lstrip("@")
    if username:
        await msg.answer(
            T.SUPPORT_FALLBACK_TO_ACCOUNT,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💬 Открыть чат заботы",
                            url=f"https://t.me/{username}",
                        ),
                    ],
                ],
            ),
        )
        return

    await msg.answer(T.SUPPORT_NO_CHANNEL)


@router.callback_query(F.data == CB_SUPPORT_CLOSE)
async def cb_close(callback: CallbackQuery) -> None:
    await callback.answer("Мы рядом, если что 💜")
    msg = callback.message
    if isinstance(msg, Message):
        try:
            await msg.delete()
        except Exception:
            pass
