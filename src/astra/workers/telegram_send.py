from pathlib import Path
from typing import Any

import httpx
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger
from astra.telegram.keyboard_policy import (
    KeyboardZone,
    reply_keyboard_for_zone,
    reply_keyboard_to_api_payload,
)
from astra.telegram.keyboards import prediction_followup_keyboard

log = get_logger(__name__)


def _inline_keyboard_to_api_payload(markup: InlineKeyboardMarkup) -> dict[str, Any]:
    return markup.model_dump(mode="json", exclude_none=True)


def _resolve_reply_markup(
    reply_markup: ReplyKeyboardMarkup | ReplyKeyboardRemove | None,
    *,
    keyboard_zone: KeyboardZone | None,
) -> dict[str, Any] | None:
    if reply_markup is not None:
        return reply_keyboard_to_api_payload(reply_markup)
    if keyboard_zone is None:
        return None
    zone_markup = reply_keyboard_for_zone(keyboard_zone)
    if zone_markup is None:
        return None
    return reply_keyboard_to_api_payload(zone_markup)


async def send_telegram_html(
    telegram_id: int,
    text: str,
    settings: Settings | None = None,
    *,
    reply_markup: ReplyKeyboardMarkup | ReplyKeyboardRemove | InlineKeyboardMarkup | None = None,
    keyboard_zone: KeyboardZone | None = KeyboardZone.MAIN,
) -> None:
    """Отправка HTML-сообщения в Telegram (worker, scheduler, уведомления)."""
    cfg = settings or get_settings()
    if not cfg.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    payload: dict[str, Any] = {
        "chat_id": telegram_id,
        "text": text,
        "parse_mode": "HTML",
    }
    if isinstance(reply_markup, InlineKeyboardMarkup):
        markup_payload = _inline_keyboard_to_api_payload(reply_markup)
    else:
        markup_payload = _resolve_reply_markup(reply_markup, keyboard_zone=keyboard_zone)
    if markup_payload is not None:
        payload["reply_markup"] = markup_payload

    url = f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendMessage"
    client_kwargs: dict[str, Any] = {"timeout": 30.0}
    if proxy := cfg.telegram_proxy_url_effective:
        client_kwargs["proxy"] = proxy
    async with httpx.AsyncClient(**client_kwargs) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
    log.info(Event.TELEGRAM_MESSAGE_SENT, telegram_id=telegram_id)


async def send_compatibility_pdf(
    telegram_id: int,
    pdf_path: Path,
    *,
    caption: str,
    settings: Settings | None = None,
) -> None:
    """Отправить PDF разбора совместимости."""
    cfg = settings or get_settings()
    if not cfg.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    url = f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendDocument"
    client_kwargs: dict[str, Any] = {"timeout": 120.0}
    if proxy := cfg.telegram_proxy_url_effective:
        client_kwargs["proxy"] = proxy

    filename = pdf_path.name
    async with httpx.AsyncClient(**client_kwargs) as client:
        with pdf_path.open("rb") as pdf_file:
            response = await client.post(
                url,
                data={"chat_id": str(telegram_id), "caption": caption},
                files={"document": (filename, pdf_file, "application/pdf")},
            )
        response.raise_for_status()
    log.info(Event.TELEGRAM_PDF_SENT, telegram_id=telegram_id, filename=filename)


async def send_prediction_to_telegram(
    telegram_id: int,
    text: str,
    settings: Settings | None = None,
) -> None:
    """Прогноз дня + inline CTA «Спросить звёзды»."""
    await send_telegram_html(
        telegram_id,
        text,
        settings,
        reply_markup=prediction_followup_keyboard(),
        keyboard_zone=None,
    )
