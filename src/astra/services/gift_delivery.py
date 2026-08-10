"""Вручение подарка новичку: что он видит в конце онбординга.

Отдельно от `gift_service`, потому что здесь есть Telegram: сервис решает,
годен ли подарок и сколько звёзд положить, а этот модуль говорит человеку.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.ask.products import SPECS
from astra.core.observability import Event, get_logger
from astra.payments.service import ask_product_code, tarot_product_code
from astra.services.gift_service import GiftRedeemed, GiftRefusal, redeem_gift
from astra.tarot.spreads import SpreadType
from astra.telegram.button_texts import (
    BTN_INVITE,
    CB_ASK_QUESTION_PREFIX,
    CB_TAROT_SPREAD_PREFIX,
)
from astra.telegram.effects import EFFECT_CELEBRATION, send_with_effect
from astra.users.models import User

log = get_logger(__name__)

# Подарок называем словами и сразу говорим, что он оплачен: «у тебя 50 ⭐» без
# имени разбора превратило бы подарок друга в непонятный бонус от бота.
_GIFT_TEXT = (
    "🎁 <b>Тебе подарок</b>\n\n"
    "Друг подарил тебе <b>{label}</b> — он уже оплачен.\n"
    "Открывай прямо сейчас или когда будешь готов: звёзды подарка ждут на "
    "твоём счету ✨"
)
# Продукт исчез из каталога после того, как его подарили: открывать нечем, и
# звать кнопку, которой нет, нельзя. Звёзды при этом на месте.
_GIFT_TEXT_NO_ENTRY = (
    "🎁 <b>Тебе подарок</b>\n\n"
    "Друг подарил тебе разбор — он уже оплачен.\n"
    "Звёзды подарка ждут на твоём счету, трать их на любой разбор ✨"
)
_OPEN_BUTTON = "🎁 Открыть подарок"

# Человек нажал «Забрать подарок» и подарка не получит. Каждый отказ говорит
# две вещи: что случилось и что делать дальше, — иначе он остаётся с молчаливым
# главным меню и уверенностью, что бот сломан. Первым делом называем причину,
# второй строкой — выход.
_REFUSAL_TEXTS: dict[GiftRefusal, str] = {
    GiftRefusal.UNKNOWN_CODE: (
        "Такую подарочную ссылку я не знаю 🕯\n\n"
        "Попроси друга прислать её заново — возможно, она потерялась по дороге."
    ),
    GiftRefusal.REVOKED: "Этот подарок отозвали 🕯\n\nПопроси друга подарить заново.",
    GiftRefusal.ALREADY_REDEEMED: (
        "Этот подарок уже забрали 🎁\n\n"
        "Если он предназначался тебе — попроси друга подарить ещё раз."
    ),
    GiftRefusal.SELF_GIFT: (
        "Это твоя же подарочная ссылка ✨\n\n"
        "Себе подарок не сработает — отправь её тому, кого в боте ещё нет."
    ),
    GiftRefusal.NOT_A_NEWCOMER: (
        "Подарок ждёт того, кого в боте ещё нет 🎁\n\n"
        "Мы с тобой уже знакомы, так что этот разбор останется новичку. "
        f"А свой можно подарить кому угодно — в разделе «{BTN_INVITE}»."
    ),
    GiftRefusal.ALREADY_GIFTED_BY_GIVER: (
        "Подарок от этого друга у тебя уже был 🎁\n\n"
        "Один подарок на пару — зато звёзды с него никуда не делись."
    ),
}


def refusal_text(refusal: GiftRefusal) -> str:
    """Что сказать человеку, чей подарок не сработал."""
    return _REFUSAL_TEXTS[refusal]


def _entry_callbacks() -> dict[str, str]:
    """Товар → кнопка, которая открывает его сценарий.

    Собирается из тех же примитивов, что и сам каталог подарков: переименуют
    продукт — карта переименуется вместе с ним, а не разъедется молча.
    """
    entries = {
        tarot_product_code(str(spread)): f"{CB_TAROT_SPREAD_PREFIX}{spread}"
        for spread in SpreadType
    }
    entries.update({ask_product_code(key): f"{CB_ASK_QUESTION_PREFIX}{key}" for key in SPECS})
    return entries


def open_gift_keyboard(product_code: str) -> InlineKeyboardMarkup | None:
    """Кнопка «Открыть подарок». None — открывать нечем.

    Ведёт в тот же callback, что и обычный вход в продукт из меню: подарок не
    заводит своей ветки сценария, он просто нажимает кнопку за человека.
    Без неё подарок был бы тупиком — новичок пять минут как в боте и меню ещё
    не знает, а искать «Три карты» руками не пойдёт.
    """
    callback = _entry_callbacks().get(product_code)
    if callback is None:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=_OPEN_BUTTON, callback_data=callback)]],
    )


async def redeem_pending_gift(
    message: Message,
    session: AsyncSession,
    user: User,
    code: str | None,
) -> GiftRedeemed | None:
    """Активировать подарок, с которым человек пришёл. None — активировать нечего.

    Код сюда попадает только из онбординга нового человека, поэтому
    `is_newcomer=True`: проверку «не зарегистрирован» сделал `/start`.

    Отказ здесь редкий — код проверялся на входе, — но не невозможный: пока
    человек регистрировался, подарок мог забрать кто-то другой. Молчать в этом
    месте нельзя: он пришёл по ссылке «Забрать подарок» и ждёт его именно
    сейчас.
    """
    if not code:
        return None
    outcome = await redeem_gift(session, code, user, is_newcomer=True)
    if not isinstance(outcome, GiftRedeemed):
        log.info(Event.GIFT_REFUSED, user_id=user.id, reason=str(outcome))
        await message.answer(refusal_text(outcome))
        return None

    keyboard = open_gift_keyboard(outcome.gift.product_code)
    await send_with_effect(
        message.answer,
        _GIFT_TEXT.format(label=outcome.label) if keyboard else _GIFT_TEXT_NO_ENTRY,
        effect=EFFECT_CELEBRATION,
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    return outcome
