"""Ссылка на Telegram-бот для CTA-кнопки в PDF."""

from __future__ import annotations

import os


def resolve_telegram_bot_url(bot_username: str | None = None) -> str:
    """Вернуть https://t.me/{username} из аргумента, settings или TELEGRAM_BOT_USERNAME."""
    if bot_username:
        return _format_telegram_url(bot_username)
    try:
        from astra.core.config import get_settings

        name = get_settings().telegram_bot_username
    except Exception:
        name = os.environ.get("TELEGRAM_BOT_USERNAME", "AstraBot")
    return _format_telegram_url(name)


def _format_telegram_url(username: str) -> str:
    return f"https://t.me/{username.strip().lstrip('@')}"
