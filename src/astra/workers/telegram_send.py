import logging

import httpx

from astra.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


async def send_telegram_html(
    telegram_id: int,
    text: str,
    settings: Settings | None = None,
) -> None:
    cfg = settings or get_settings()
    if not cfg.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    url = f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            json={
                "chat_id": telegram_id,
                "text": text,
                "parse_mode": "HTML",
            },
        )
        response.raise_for_status()
    logger.info("Sent Telegram message to %s", telegram_id)
