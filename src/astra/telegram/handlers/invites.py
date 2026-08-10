"""Раздел «Пригласить друга»: подарить разбор, позвать по ссылке, свой счёт.

Раздел живёт в одном редактируемом экране. Исключение — сама подарочная
ссылка: она приходит **отдельным сообщением**, потому что её пересылают
дальше. Экран для этого не годится: он исчезнет на следующем шаге, а вместе с
ним и подарок.
"""

from __future__ import annotations

from urllib.parse import quote

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import get_settings
from astra.gifts import crud as gifts_crud
from astra.referrals.getters import get_referral_stats
from astra.services.gift_service import giftable_products, issue_gift, product_label
from astra.telegram.button_texts import (
    BTN_INVITE,
    CB_INVITE_GIFT,
    CB_INVITE_GIFT_PICK_PREFIX,
    CB_INVITE_HUB,
    CB_INVITE_LINK,
)
from astra.telegram.effects import EFFECT_CELEBRATION, send_with_effect
from astra.telegram.keyboards import (
    gift_products_keyboard,
    invite_back_keyboard,
    invite_hub_keyboard,
)
from astra.telegram.screen import alert, close_screen, show_screen, toast
from astra.users import crud as users_crud
from astra.wallet.crud import get_balance

router = Router(name="invites")

INVITE_SCREEN = "invite"

_HUB_TEXT = (
    "🎁 <b>Приглашения</b>\n\n"
    "Подари другу разбор — за мой счёт. Когда он придёт и вернётся на второй "
    "день, тебе капнут звёзды: их можно тратить на любые разборы.\n\n"
    "На счету: <b>{balance} ⭐</b>\n"
    "Пришло по твоим ссылкам: <b>{invited}</b>\n"
    "Подарков забрали: <b>{redeemed}</b>"
)
_PICK_TEXT = "🎁 <b>Что подарить?</b>\n\nДруг получит этот разбор бесплатно."
_LIMIT_TEXT = (
    "Слишком много подарков ждут своего часа 🕯\n\n"
    "Дождись, пока заберут выданные, — и дари дальше, сколько захочешь."
)
_LINK_TEXT = (
    "🔗 <b>Твоя ссылка</b>\n\n"
    "<code>{link}</code>\n\n"
    "Тот, кто придёт по ней и вернётся на второй день, принесёт тебе "
    "<b>{reward} ⭐</b>."
)
# Сообщение, которое человек пересылает другу. Ни слова про реферальную
# программу: подарок должен читаться как подарок, а не как приглашение в
# схему. Ссылка — на кнопке, чтобы в тексте не было технического мусора.
_GIFT_CARD_TEXT = (
    "🎁 <b>Тебе подарок</b>\n\n"
    "Держи разбор от Астрид — <b>{label}</b>. Он уже оплачен, тебе останется "
    "только открыть.\n\n"
    "Астрид — астролог в Telegram: смотрит, что происходит в небе, "
    "и рассказывает по-человечески ✨"
)
_GIFT_SENT_TEXT = (
    "Готово ✨ Перешли сообщение выше тому, кому даришь.\n\n"
    "Подарок сработает только у того, кого в боте ещё нет."
)
_NO_USER_TEXT = "Сначала давай познакомимся — жми /start ✨"


def _gift_link(code: str) -> str:
    username = get_settings().telegram_bot_username.lstrip("@")
    return f"https://t.me/{username}?start=gift_{code}"


def _gift_card_keyboard(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Забрать подарок", url=_gift_link(code))],
        ],
    )


async def _show_hub(message: Message, session: AsyncSession, user) -> None:  # noqa: ANN001
    stats = await get_referral_stats(session, user.id)
    text = _HUB_TEXT.format(
        balance=await get_balance(session, user.id),
        invited=stats.invited_count,
        redeemed=await gifts_crud.count_redeemed(session, user.id),
    )
    await show_screen(
        message,
        text,
        scope=INVITE_SCREEN,
        parse_mode="HTML",
        reply_markup=invite_hub_keyboard(),
    )


@router.message(F.text == BTN_INVITE)
async def open_invites(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await users_crud.get_user_by_telegram_id(session, message.from_user.id)
    if user is None:
        await message.answer(_NO_USER_TEXT)
        return
    await state.clear()
    await _show_hub(message, session, user)


@router.callback_query(F.data == CB_INVITE_HUB)
async def cb_invite_hub(callback: CallbackQuery, session: AsyncSession) -> None:
    if not isinstance(callback.message, Message) or callback.from_user is None:
        await toast(callback)
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await alert(callback, _NO_USER_TEXT)
        return
    await toast(callback)
    await _show_hub(callback.message, session, user)


@router.callback_query(F.data == CB_INVITE_GIFT)
async def cb_pick_gift(callback: CallbackQuery) -> None:
    await toast(callback)
    if isinstance(callback.message, Message):
        await show_screen(
            callback.message,
            _PICK_TEXT,
            scope=INVITE_SCREEN,
            parse_mode="HTML",
            reply_markup=gift_products_keyboard(giftable_products()),
        )


@router.callback_query(F.data == CB_INVITE_LINK)
async def cb_invite_link(callback: CallbackQuery, session: AsyncSession) -> None:
    if not isinstance(callback.message, Message) or callback.from_user is None:
        await toast(callback)
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await alert(callback, _NO_USER_TEXT)
        return
    await toast(callback)
    stats = await get_referral_stats(session, user.id)
    share_url = (
        f"https://t.me/share/url?url={stats.referral_link}"
        f"&text={quote('Астрид смотрит, что происходит в небе, и рассказывает по-человечески ✨')}"
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Отправить другу", url=share_url)],
            *invite_back_keyboard().inline_keyboard,
        ],
    )
    await show_screen(
        callback.message,
        _LINK_TEXT.format(
            link=stats.referral_link,
            reward=get_settings().referral_reward_stars,
        ),
        scope=INVITE_SCREEN,
        parse_mode="HTML",
        reply_markup=markup,
    )


@router.callback_query(F.data.startswith(CB_INVITE_GIFT_PICK_PREFIX))
async def cb_issue_gift(callback: CallbackQuery, session: AsyncSession) -> None:
    if not isinstance(callback.message, Message) or callback.from_user is None:
        await toast(callback)
        return
    product_code = (callback.data or "").removeprefix(CB_INVITE_GIFT_PICK_PREFIX)
    if product_code not in {p.code for p in giftable_products()}:
        await toast(callback)
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await alert(callback, _NO_USER_TEXT)
        return

    gift = await issue_gift(session, user, product_code)
    if gift is None:
        await toast(callback)
        await show_screen(
            callback.message,
            _LIMIT_TEXT,
            scope=INVITE_SCREEN,
            parse_mode="HTML",
            reply_markup=invite_back_keyboard(),
        )
        return
    await session.commit()
    await toast(callback)

    # Экран гасим: подарочная карточка должна остаться в чате навсегда — её
    # пересылают, и исчезни она, исчезнет и подарок.
    await close_screen(callback.message, INVITE_SCREEN)
    await send_with_effect(
        callback.message.answer,
        _GIFT_CARD_TEXT.format(label=product_label(product_code)),
        effect=EFFECT_CELEBRATION,
        parse_mode="HTML",
        reply_markup=_gift_card_keyboard(gift.code),
    )
    await callback.message.answer(_GIFT_SENT_TEXT)
