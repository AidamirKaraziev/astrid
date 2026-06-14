"""Флаг «предсказание в работе» — защита от дублей в RabbitMQ и повторных отправок."""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from redis.asyncio import Redis

from astra.core.config import get_settings

logger = logging.getLogger(__name__)

_PENDING_TTL_SEC = 2700
_KEY_PREFIX = "astra:prediction:pending"


def _pending_key(user_id: UUID, prediction_date: date) -> str:
    return f"{_KEY_PREFIX}:{user_id}:{prediction_date.isoformat()}"


async def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


async def try_mark_prediction_pending(user_id: UUID, prediction_date: date) -> bool:
    """True — мы первые; False — генерация/отправка уже запущена."""
    client = await _redis()
    try:
        acquired = await client.set(
            _pending_key(user_id, prediction_date),
            "1",
            nx=True,
            ex=_PENDING_TTL_SEC,
        )
        return bool(acquired)
    finally:
        await client.aclose()


async def is_prediction_pending(user_id: UUID, prediction_date: date) -> bool:
    client = await _redis()
    try:
        return bool(await client.exists(_pending_key(user_id, prediction_date)))
    finally:
        await client.aclose()


async def clear_prediction_pending(user_id: UUID, prediction_date: date) -> None:
    client = await _redis()
    try:
        await client.delete(_pending_key(user_id, prediction_date))
    finally:
        await client.aclose()
        logger.debug("cleared prediction pending %s %s", user_id, prediction_date)
