"""Кэш file_id картинок карт в Redis: одна заливка на карту, дальше по id.

Общий для бота (aiogram) и worker'а (прямой Bot API) — иначе карта дня из
рассылки заливала бы файл заново каждое утро.
При смене bot token file_id протухают — сбросить ключи:
    redis-cli --scan --pattern 'astra:telegram:tarot:file_id:*' | xargs redis-cli del
"""

from __future__ import annotations

from redis.asyncio import Redis

from astra.core.config import get_settings

FILE_ID_KEY = "astra:telegram:tarot:file_id:{card_id}"


async def get_cached_file_id(card_id: str) -> str | None:
    client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        return await client.get(FILE_ID_KEY.format(card_id=card_id))
    finally:
        await client.aclose()


async def cache_file_id(card_id: str, file_id: str) -> None:
    client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        await client.set(FILE_ID_KEY.format(card_id=card_id), file_id)
    finally:
        await client.aclose()
