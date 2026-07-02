"""Redis: message_id последнего progress-сообщения в чате."""

from __future__ import annotations

import logging
from uuid import UUID

from redis.asyncio import Redis

from astra.core.config import get_settings

logger = logging.getLogger(__name__)

_PROGRESS_TTL_SEC = 2700
_KEY_PREFIX = "astra:progress"


def progress_redis_key(user_id: UUID, job_key: str) -> str:
    return f"{_KEY_PREFIX}:{user_id}:{job_key}"


async def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


async def get_progress_message_id(user_id: UUID, job_key: str) -> int | None:
    client = await _redis()
    try:
        raw = await client.get(progress_redis_key(user_id, job_key))
        if raw is None:
            return None
        return int(raw)
    finally:
        await client.aclose()


async def set_progress_message_id(
    user_id: UUID,
    job_key: str,
    message_id: int,
) -> None:
    client = await _redis()
    try:
        await client.set(
            progress_redis_key(user_id, job_key),
            str(message_id),
            ex=_PROGRESS_TTL_SEC,
        )
    finally:
        await client.aclose()


async def clear_progress_message_id(user_id: UUID, job_key: str) -> int | None:
    """Удалить ключ; вернуть прежний message_id (для delete в Telegram)."""
    client = await _redis()
    try:
        key = progress_redis_key(user_id, job_key)
        raw = await client.get(key)
        await client.delete(key)
        if raw is None:
            return None
        return int(raw)
    finally:
        await client.aclose()
        logger.debug("cleared progress key user=%s job=%s", user_id, job_key)
