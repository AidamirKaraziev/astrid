"""Низкоуровневые вызовы Telegram Bot API (worker + bot)."""

from __future__ import annotations

from typing import Any

import httpx
from aiogram.types import InlineKeyboardMarkup

from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger

log = get_logger(__name__)


def _client_kwargs(settings: Settings, *, timeout: float = 30.0) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"timeout": timeout}
    if proxy := settings.telegram_proxy_url_effective:
        kwargs["proxy"] = proxy
    return kwargs


def _api_url(method: str, settings: Settings) -> str:
    return f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"


async def send_html_message(
    chat_id: int,
    text: str,
    *,
    settings: Settings | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> int | None:
    """Отправить HTML-сообщение, вернуть message_id."""
    cfg = settings or get_settings()
    if not cfg.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup.model_dump(mode="json", exclude_none=True)

    async with httpx.AsyncClient(**_client_kwargs(cfg)) as client:
        response = await client.post(_api_url("sendMessage", cfg), json=payload)
        response.raise_for_status()
        data = response.json()
    if not data.get("ok"):
        return None
    result = data.get("result") or {}
    message_id = result.get("message_id")
    return int(message_id) if message_id is not None else None


async def delete_message(
    chat_id: int,
    message_id: int,
    *,
    settings: Settings | None = None,
) -> bool:
    cfg = settings or get_settings()
    if not cfg.telegram_bot_token:
        return False
    payload = {"chat_id": chat_id, "message_id": message_id}
    try:
        async with httpx.AsyncClient(**_client_kwargs(cfg)) as client:
            response = await client.post(_api_url("deleteMessage", cfg), json=payload)
            if response.status_code == 400:
                return False
            response.raise_for_status()
        return True
    except Exception:
        log.debug(Event.TELEGRAM_API_FAILED, method="deleteMessage", chat_id=chat_id, message_id=message_id, exc_info=True)
        return False


async def send_chat_action_typing(
    chat_id: int,
    *,
    settings: Settings | None = None,
) -> None:
    cfg = settings or get_settings()
    if not cfg.telegram_bot_token:
        return
    payload = {"chat_id": chat_id, "action": "typing"}
    try:
        async with httpx.AsyncClient(**_client_kwargs(cfg, timeout=10.0)) as client:
            await client.post(_api_url("sendChatAction", cfg), json=payload)
    except Exception:
        log.debug(Event.TELEGRAM_API_FAILED, method="sendChatAction", chat_id=chat_id, exc_info=True)
