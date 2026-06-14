"""Уведомление пользователя, если генерация предсказания затянулась."""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from redis.asyncio import Redis

from astra.core.config import get_settings
from astra.workers.telegram_send import send_telegram_html

logger = logging.getLogger(__name__)

PREDICTION_DELAYED_NOTIFY_TEXT = (
    "Чуть дольше обычного ✨\n"
    "Твоё предсказание ещё готовится — постараюсь прислать как можно скорее."
)

PREDICTION_FINAL_FAILURE_TEXT = (
    "Не получилось сгенерировать прогноз прямо сейчас.\n"
    "Нажми 🔮 <b>Предсказание на сегодня</b> через пару минут — попробую снова."
)

_DELAYED_KEY_PREFIX = "astra:prediction:delayed_notified"
_DELAYED_TTL_SEC = 2700


def _delayed_key(user_id: UUID, prediction_date: date) -> str:
    return f"{_DELAYED_KEY_PREFIX}:{user_id}:{prediction_date.isoformat()}"


async def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


async def maybe_send_delayed_notification(
    user_id: UUID,
    telegram_id: int,
    prediction_date: date,
) -> bool:
    """Один раз за день сообщить, что генерация занимает дольше обычного."""
    client = await _redis()
    try:
        acquired = await client.set(
            _delayed_key(user_id, prediction_date),
            "1",
            nx=True,
            ex=_DELAYED_TTL_SEC,
        )
        if not acquired:
            return False
    finally:
        await client.aclose()

    try:
        await send_telegram_html(telegram_id, PREDICTION_DELAYED_NOTIFY_TEXT)
    except Exception:
        logger.exception(
            "failed to send delayed prediction notice to telegram_id=%s",
            telegram_id,
        )
        return False

    logger.info(
        "sent delayed prediction notice user=%s date=%s",
        user_id,
        prediction_date,
    )
    return True


async def send_final_failure_notification(telegram_id: int) -> None:
    try:
        await send_telegram_html(telegram_id, PREDICTION_FINAL_FAILURE_TEXT)
    except Exception:
        logger.exception(
            "failed to send final failure notice to telegram_id=%s",
            telegram_id,
        )
