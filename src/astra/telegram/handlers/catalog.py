from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery

from astra.core.observability import Event, get_logger
from astra.telegram.button_texts import (
    BTN_BACK_MENU,
    BTN_BACK_MENU_LEGACY,
    BTN_COMPATIBILITY,
    BTN_NATAL,
    BTN_TAROT,
    CB_PRODUCT_ASK_STARS,
    COMING_SOON_TEXT,
    PAID_PRODUCT_BUTTONS,
)
from astra.telegram.keyboards import main_menu_keyboard, support_contextual_keyboard
from astra.telegram.screen import toast

log = get_logger(__name__)

router = Router(name="catalog")

_PAID_STUB_BUTTONS = frozenset(PAID_PRODUCT_BUTTONS) - {BTN_TAROT, BTN_COMPATIBILITY, BTN_NATAL}


@router.message(F.text.in_({BTN_BACK_MENU, BTN_BACK_MENU_LEGACY}))
async def back_to_main_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Главное меню ✨", reply_markup=main_menu_keyboard())


@router.message(F.text == BTN_TAROT)
async def open_tarot_menu(message: Message) -> None:
    # Раздел живёт в одном редактируемом экране: расклады — inline-кнопки на нём.
    from astra.telegram.handlers.tarot_spreads import open_spreads_screen

    await open_spreads_screen(message)


@router.message(F.text.in_(_PAID_STUB_BUTTONS))
async def product_coming_soon(message: Message) -> None:
    await message.answer(COMING_SOON_TEXT)


@router.callback_query(F.data == CB_PRODUCT_ASK_STARS)
async def cb_product_ask_stars(callback: CallbackQuery) -> None:
    await toast(callback, COMING_SOON_TEXT)


# Страховка: платёж с payload, который не подхватил ни один профильный хендлер
# (таро, колесо…). До списания — отклоняем; после списания — возвращаем звёзды.


@router.pre_checkout_query()
async def pre_checkout_unknown_payload(query: PreCheckoutQuery) -> None:
    log.warning(Event.PAYMENT_PRE_CHECKOUT_REJECTED, reason="unknown_payload")
    await query.answer(ok=False, error_message="Платёж устарел — начни покупку заново ✨")


@router.message(F.successful_payment)
async def successful_payment_orphan(message: Message) -> None:
    payment_info = message.successful_payment
    if payment_info is None or message.from_user is None or message.bot is None:
        return
    log.error(
        Event.PAYMENT_ORPHAN,
        reason="unhandled_payload",
        charge_id=payment_info.telegram_payment_charge_id,
    )
    await message.bot.refund_star_payment(
        user_id=message.from_user.id,
        telegram_payment_charge_id=payment_info.telegram_payment_charge_id,
    )
    await message.answer(
        "Кажется, покупка не завершилась — мы вернули звёзды ⭐\n"
        "Если что-то не так, мы рядом:",
        reply_markup=support_contextual_keyboard(),
    )
