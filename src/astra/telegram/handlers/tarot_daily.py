"""Кнопка «Спросить карты» под ежедневным прогнозом."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.observability import get_logger
from astra.services.tarot_daily_service import format_tarot_reveal, reveal_daily_card
from astra.telegram.keyboards import CB_TAROT_DAILY
from astra.users import crud as users_crud

log = get_logger(__name__)

router = Router(name="tarot_daily")

_FAIL_TEXT = "Карты сегодня молчат — попробуй ещё раз через минуту 🌙"


@router.callback_query(F.data == CB_TAROT_DAILY)
async def cb_tarot_daily(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None or user.profile is None:
        await callback.answer("Сначала: /start", show_alert=True)
        return

    await callback.answer("Тасую колоду под твоё небо…")

    today = datetime.now(ZoneInfo(user.profile.timezone)).date()
    outcome = await reveal_daily_card(session, user, today)

    if outcome.draw is None or outcome.card is None:
        if outcome.failure_reason == "in_progress":
            return  # уже тянется — второе сообщение не шлём
        await callback.message.answer(_FAIL_TEXT)
        return

    await session.commit()
    await callback.message.answer(
        format_tarot_reveal(
            outcome.card,
            outcome.draw.interpretation or "",
            repeated=outcome.already_drawn,
        ),
        parse_mode="HTML",
    )
