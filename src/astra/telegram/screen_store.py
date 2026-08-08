"""Redis: message_id живого экрана раздела и его тип.

Экран переживает рестарт процесса и живёт дольше одного апдейта, поэтому
message_id лежит в Redis, а не в памяти и не в FSM: воркер и бот — разные
процессы, а состояние FSM чистится при выходе из сценария, тогда как экран
надо погасить даже после `state.clear()`.

Тип экрана (`text` или `media`) хранится рядом: Telegram не превращает
текстовое сообщение в медиа и обратно, поэтому при смене типа экран
пересоздаётся, а не редактируется.
"""

from __future__ import annotations

from enum import StrEnum

from redis.asyncio import Redis

from astra.core.config import get_settings
from astra.core.observability import Event, get_logger

log = get_logger(__name__)

# Экран живёт столько же, сколько progress-сообщение: дольше суток он всё
# равно бесполезен — Telegram не даёт редактировать сообщения старше 48 часов.
_SCREEN_TTL_SEC = 2700
_KEY_PREFIX = "astra:screen"


class ScreenKind(StrEnum):
    TEXT = "text"
    MEDIA = "media"


class Screen:
    """Что записано в реестре: id сообщения и его тип."""

    __slots__ = ("kind", "message_id")

    def __init__(self, message_id: int, kind: ScreenKind) -> None:
        self.message_id = message_id
        self.kind = kind

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Screen):
            return NotImplemented
        return self.message_id == other.message_id and self.kind is other.kind

    def __repr__(self) -> str:
        return f"Screen({self.message_id}, {self.kind})"


def screen_redis_key(chat_id: int, scope: str) -> str:
    return f"{_KEY_PREFIX}:{chat_id}:{scope}"


async def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def _parse(raw: str | None) -> Screen | None:
    if not raw:
        return None
    message_id, _, kind = raw.partition(":")
    try:
        return Screen(int(message_id), ScreenKind(kind or ScreenKind.TEXT))
    except ValueError:
        return None


async def get_screen(chat_id: int, scope: str) -> Screen | None:
    client = await _redis()
    try:
        return _parse(await client.get(screen_redis_key(chat_id, scope)))
    finally:
        await client.aclose()


async def set_screen(chat_id: int, scope: str, message_id: int, kind: ScreenKind) -> None:
    client = await _redis()
    try:
        await client.set(
            screen_redis_key(chat_id, scope),
            f"{message_id}:{kind.value}",
            ex=_SCREEN_TTL_SEC,
        )
    finally:
        await client.aclose()


async def clear_screen(chat_id: int, scope: str) -> Screen | None:
    """Удалить ключ; вернуть прежний экран (для deleteMessage в Telegram)."""
    client = await _redis()
    try:
        key = screen_redis_key(chat_id, scope)
        raw = await client.get(key)
        await client.delete(key)
        return _parse(raw)
    finally:
        await client.aclose()
        log.debug(Event.REDIS_SCREEN_CLEARED, chat_id=chat_id, scope=scope)
