"""Автоприкрепление актуальной Reply-клавиатуры к ответам бота."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject

from astra.telegram.keyboard_policy import (
    KeyboardZone,
    reply_keyboard_for_zone,
    resolve_keyboard_zone,
)

_PATCHED_ATTR = "_astra_auto_keyboard_patched"


class AutoKeyboardMiddleware(BaseMiddleware):
    """Подставляет reply_markup, если хендлер не задал его явно.

    Telegram хранит клавиатуру на клиенте; без этого middleware пользователь
    видит устаревшие кнопки до /start.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        message = _event_message(event)
        if message is not None:
            await self._patch_message_answer(message, data)
        return await handler(event, data)

    async def _patch_message_answer(self, message: Message, data: dict[str, Any]) -> None:
        original_answer = message.answer
        if getattr(original_answer, _PATCHED_ATTR, False):
            return

        zone = await self._zone_for_event(message, data)
        skip = zone is None

        async def answer(text: str = "", **kwargs: Any):
            if not skip and "reply_markup" not in kwargs:
                keyboard = reply_keyboard_for_zone(zone)
                if keyboard is not None:
                    kwargs["reply_markup"] = keyboard
            return await original_answer(text, **kwargs)

        answer.__setattr__(_PATCHED_ATTR, True)
        object.__setattr__(message, "answer", answer)

    async def _zone_for_event(self, message: Message, data: dict[str, Any]) -> KeyboardZone | None:
        handler = data.get("handler")
        skip_flag = bool(getattr(handler, "flags", {}).get("skip_auto_keyboard"))
        fsm: FSMContext | None = data.get("state")
        fsm_state = None
        if fsm is not None:
            fsm_state = await fsm.get_state()
        return resolve_keyboard_zone(
            incoming_text=message.text,
            fsm_state=fsm_state,
            skip_auto_keyboard=skip_flag,
        )


def _event_message(event: TelegramObject) -> Message | None:
    if isinstance(event, Message):
        return event
    if isinstance(event, CallbackQuery) and isinstance(event.message, Message):
        return event.message
    return None
