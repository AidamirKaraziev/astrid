"""Отметка активности на каждом входящем апдейте.

Одна точка вместо десятка вызовов по хендлерам: раньше серию двигал только
`/start`, и человек, который ежедневно жал кнопки, навсегда видел «серия 1».

Считаем только личку: сообщения из группы операторов и служебные апдейты —
это наша работа, а не активность пользователя. Ошибка отметки никогда не
роняет обработку самого апдейта: аналитика не стоит того, чтобы человек
вместо расклада увидел молчание.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from astra.core.observability import get_logger
from astra.usage.activity import mark_active
from astra.users import crud as users_crud

log = get_logger(__name__)


def _actor(event: TelegramObject) -> tuple[int, bool] | None:
    """(telegram_id, это личка) для апдейтов, которые сделал человек."""
    if isinstance(event, Update):
        event = event.event  # type: ignore[assignment]

    if isinstance(event, Message):
        if event.from_user is None or event.from_user.is_bot:
            return None
        return event.from_user.id, event.chat.type == "private"

    if isinstance(event, CallbackQuery):
        if event.from_user is None or event.from_user.is_bot:
            return None
        private = event.message is None or event.message.chat.type == "private"
        return event.from_user.id, private

    # Оплаты (pre_checkout, successful_payment) приходят внутри Message,
    # поэтому отдельной ветки им не нужно.
    return None


class ActivityMiddleware(BaseMiddleware):
    """Пишет день активности и продлевает серию; хендлеры об этом не знают."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session = data.get("session")
        actor = _actor(event)

        if session is not None and actor is not None:
            telegram_id, private = actor
            if private:
                try:
                    user = await users_crud.get_user_by_telegram_id(session, telegram_id)
                    if user is not None:
                        await mark_active(session, user)
                except Exception:
                    log.exception("activity.mark_failed", telegram_id=telegram_id)

        return await handler(event, data)
