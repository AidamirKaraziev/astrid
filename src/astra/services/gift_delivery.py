"""Вручение подарка новичку: что он видит в конце онбординга.

Отдельно от `gift_service`, потому что здесь есть Telegram: сервис решает,
годен ли подарок и сколько звёзд положить, а этот модуль говорит человеку.
"""

from __future__ import annotations

from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.observability import Event, get_logger
from astra.services.gift_service import GiftRedeemed, redeem_gift
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


async def redeem_pending_gift(
    message: Message,
    session: AsyncSession,
    user: User,
    code: str | None,
) -> GiftRedeemed | None:
    """Активировать подарок, с которым человек пришёл. None — активировать нечего.

    Код сюда попадает только из онбординга нового человека, поэтому
    `is_newcomer=True`: проверку «не зарегистрирован» сделал `/start`.
    """
    if not code:
        return None
    outcome = await redeem_gift(session, code, user, is_newcomer=True)
    if not isinstance(outcome, GiftRedeemed):
        log.info(Event.GIFT_REFUSED, user_id=user.id, reason=str(outcome))
        return None

    await send_with_effect(
        message.answer,
        _GIFT_TEXT.format(label=outcome.label),
        effect=EFFECT_CELEBRATION,
        parse_mode="HTML",
    )
    return outcome
