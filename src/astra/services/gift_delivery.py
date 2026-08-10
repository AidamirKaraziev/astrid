"""Вручение подарка новичку: что он видит в конце онбординга.

Отдельно от `gift_service`, потому что здесь есть Telegram: сервис решает,
годен ли подарок и сколько звёзд положить, а этот модуль говорит человеку.
"""

from __future__ import annotations

from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.observability import Event, get_logger
from astra.services.gift_service import GiftRedeemed, GiftRefusal, redeem_gift
from astra.telegram.button_texts import BTN_INVITE
from astra.telegram.effects import EFFECT_CELEBRATION, send_with_effect
from astra.users.models import User

log = get_logger(__name__)

# Подарок называем словами и сразу говорим, что он оплачен: «у тебя 50 ⭐» без
# имени разбора превратило бы подарок друга в непонятный бонус от бота.
_GIFT_TEXT = (
    "🎁 <b>Тебе подарок</b>\n\n"
    "Друг подарил тебе <b>{label}</b> — он уже оплачен.\n"
    "Открывай, когда будешь готов: звёзды подарка ждут на твоём счету ✨"
)

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

    await send_with_effect(
        message.answer,
        _GIFT_TEXT.format(label=outcome.label),
        effect=EFFECT_CELEBRATION,
        parse_mode="HTML",
    )
    return outcome
