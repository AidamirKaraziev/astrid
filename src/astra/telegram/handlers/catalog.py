from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from astra.core.config import get_settings
from astra.telegram.button_texts import (
    BTN_BACK_MENU,
    BTN_TAROT,
    BTN_TAROT_DECISION,
    BTN_TAROT_RELATIONS,
    BTN_TAROT_THREE,
    CB_PRODUCT_ASK_STARS,
    COMING_SOON_TEXT,
    PAID_PRODUCT_BUTTONS,
    TAROT_PRODUCT_BUTTONS,
)
from astra.telegram.help_text import (
    HELP_CARD_FOOTER_WITH_SUPPORT,
    HELP_CARD_NO_SUPPORT,
    HELP_CARD_TEXT,
)
from astra.telegram.keyboards import help_keyboard, main_menu_keyboard, tarot_keyboard

router = Router(name="catalog")

_PAID_STUB_BUTTONS = frozenset(PAID_PRODUCT_BUTTONS) - {BTN_TAROT}
_TAROT_STUB_BUTTONS = frozenset(TAROT_PRODUCT_BUTTONS)


async def show_help(message: Message) -> None:
    """Помощь — только через /help (Menu Button)."""
    username = get_settings().telegram_support_username.strip().lstrip("@")
    if username:
        text = HELP_CARD_TEXT + HELP_CARD_FOOTER_WITH_SUPPORT
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=help_keyboard(username),
        )
        return
    await message.answer(
        HELP_CARD_TEXT + HELP_CARD_NO_SUPPORT,
        parse_mode="HTML",
    )


@router.message(F.text == BTN_BACK_MENU)
async def back_to_main_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Главное меню ✨", reply_markup=main_menu_keyboard())


@router.message(F.text == BTN_TAROT)
async def open_tarot_menu(message: Message) -> None:
    await message.answer("Выбери расклад ✨", reply_markup=tarot_keyboard())


@router.message(F.text.in_(_PAID_STUB_BUTTONS | _TAROT_STUB_BUTTONS))
async def product_coming_soon(message: Message) -> None:
    await message.answer(COMING_SOON_TEXT)


@router.callback_query(F.data == CB_PRODUCT_ASK_STARS)
async def cb_product_ask_stars(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(COMING_SOON_TEXT)
