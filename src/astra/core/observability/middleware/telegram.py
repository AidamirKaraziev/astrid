"""Telegram middleware: correlation_id и lifecycle update."""

from __future__ import annotations

import time
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from astra.core.observability.context import bound_context
from astra.core.observability.events import Event
from astra.core.observability.logging import get_logger
from astra.core.sentry import set_sentry_user

log = get_logger(__name__)


class TelegramObservabilityMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)

        correlation_id = f"upd-{event.update_id}"
        user = None
        if event.message and event.message.from_user:
            user = event.message.from_user
        elif event.callback_query and event.callback_query.from_user:
            user = event.callback_query.from_user

        context_kwargs: dict[str, Any] = {"correlation_id": correlation_id}
        if user is not None:
            context_kwargs["telegram_id"] = user.id
        set_sentry_user(user.id if user else None)

        with bound_context(**context_kwargs):
            started = time.perf_counter()
            log.info(
                Event.TELEGRAM_UPDATE_RECEIVED,
                update_id=event.update_id,
                update_type=event.event_type,
                telegram_id=user.id if user else None,
            )
            try:
                result = await handler(event, data)
                duration_ms = round((time.perf_counter() - started) * 1000)
                log.info(
                    Event.TELEGRAM_UPDATE_COMPLETED,
                    update_id=event.update_id,
                    duration_ms=duration_ms,
                )
                return result
            except Exception:
                duration_ms = round((time.perf_counter() - started) * 1000)
                log.exception(
                    Event.TELEGRAM_UPDATE_FAILED,
                    update_id=event.update_id,
                    duration_ms=duration_ms,
                )
                raise
