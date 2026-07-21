import json
from pathlib import Path
from typing import Any

import httpx
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger
from astra.tarot.file_id_cache import cache_file_id, get_cached_file_id
from astra.telegram.keyboard_policy import (
    KeyboardZone,
    reply_keyboard_for_zone,
    reply_keyboard_to_api_payload,
)
from astra.telegram.keyboards import prediction_followup_keyboard

log = get_logger(__name__)


class BotBlockedError(Exception):
    """Telegram вернул 403: пользователь заблокировал бота.

    Перманентная ошибка — ретраи бессмысленны; консьюмер помечает пользователя
    (users.bot_blocked_at) и подтверждает задачу без requeue.
    """

    def __init__(self, telegram_id: int) -> None:
        super().__init__(f"bot blocked by user {telegram_id}")
        self.telegram_id = telegram_id


def _raise_for_status(response: httpx.Response, telegram_id: int) -> None:
    if response.status_code == 403:
        raise BotBlockedError(telegram_id)
    response.raise_for_status()


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
        _raise_for_status(response, telegram_id)
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
        _raise_for_status(response, telegram_id)
    log.info(Event.TELEGRAM_PDF_SENT, telegram_id=telegram_id, filename=filename)


async def send_card_photo_to_telegram(
    telegram_id: int,
    card_id: str,
    image: Path | None,
    *,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    settings: Settings | None = None,
) -> None:
    """Карта дня фото + inline-кнопка; без ассета — текстом (ритуал важнее картинки).

    Первая отправка заливает файл, дальше — по file_id из общего кэша
    (astra.tarot.file_id_cache), как в боте.
    """
    cfg = settings or get_settings()
    if not cfg.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    if image is None:
        await send_telegram_html(
            telegram_id,
            caption,
            cfg,
            reply_markup=reply_markup,
            keyboard_zone=None,
        )
        return

    cached_file_id = await get_cached_file_id(card_id)
    data: dict[str, Any] = {
        "chat_id": str(telegram_id),
        "caption": caption,
        "parse_mode": "HTML",
    }
    if reply_markup is not None:
        data["reply_markup"] = json.dumps(
            _inline_keyboard_to_api_payload(reply_markup),
            ensure_ascii=False,
        )

    url = f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendPhoto"
    client_kwargs: dict[str, Any] = {"timeout": 60.0}
    if proxy := cfg.telegram_proxy_url_effective:
        client_kwargs["proxy"] = proxy

    async with httpx.AsyncClient(**client_kwargs) as client:
        if cached_file_id:
            response = await client.post(url, data={**data, "photo": cached_file_id})
        else:
            with image.open("rb") as photo_file:
                response = await client.post(
                    url,
                    data=data,
                    files={"photo": (image.name, photo_file, "image/jpeg")},
                )
        _raise_for_status(response, telegram_id)
        payload = response.json()

    if not cached_file_id:
        sizes = (payload.get("result") or {}).get("photo") or []
        if sizes:
            await cache_file_id(card_id, sizes[-1]["file_id"])
    log.info(Event.TELEGRAM_MESSAGE_SENT, telegram_id=telegram_id)


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
