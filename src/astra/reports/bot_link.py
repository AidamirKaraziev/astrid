"""Ссылка на Telegram-бот для CTA-кнопки в PDF.

PDF пересылают дальше — это самый живой канал распространения из всех, что у
нас есть. Поэтому в кнопку зашивается реферальный код владельца разбора:
перешёл по чужому PDF — стал его приглашённым.
"""

from __future__ import annotations

import os


def resolve_telegram_bot_url(
    bot_username: str | None = None,
    referral_code: str | None = None,
) -> str:
    """https://t.me/{username} из аргумента, settings или TELEGRAM_BOT_USERNAME.

    С `referral_code` — персональная ссылка владельца разбора.
    """
    if bot_username:
        return _format_telegram_url(bot_username, referral_code)
    try:
        from astra.core.config import get_settings

        name = get_settings().telegram_bot_username
    except Exception:
        name = os.environ.get("TELEGRAM_BOT_USERNAME", "AstraBot")
    return _format_telegram_url(name, referral_code)


def _format_telegram_url(username: str, referral_code: str | None = None) -> str:
    url = f"https://t.me/{username.strip().lstrip('@')}"
    return f"{url}?start=ref_{referral_code}" if referral_code else url
