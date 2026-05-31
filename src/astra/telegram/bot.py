from typing import Any

import logging

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import TelegramObject, Update
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from astra.core.config import Settings
from astra.db.session import get_session_factory
from astra.telegram.handlers import menu, onboarding, places, start
from astra.telegram.middlewares import DbSessionMiddleware

logger = logging.getLogger(__name__)


class UpdateLoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if isinstance(event, Update):
            logger.info("Telegram update id=%s type=%s", event.update_id, event.event_type)
        return await handler(event, data)


def create_bot(settings: Settings) -> Bot:
    session: AiohttpSession | None = None
    if settings.telegram_proxy_url:
        session = AiohttpSession(proxy=settings.telegram_proxy_url)
        logger.info("Telegram Bot API via proxy (host hidden in logs)")
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )


async def build_fsm_storage(settings: Settings) -> BaseStorage:
    """Redis для FSM; если недоступен — MemoryStorage (dev без docker)."""
    if settings.fsm_storage == "memory":
        logger.info("FSM storage: MemoryStorage (configured)")
        return MemoryStorage()

    try:
        redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        await redis.ping()
        logger.info("FSM storage: Redis")
        return RedisStorage(redis=redis)
    except Exception as exc:
        logger.warning(
            "Redis недоступен (%s). FSM → MemoryStorage. "
            "Для prod запустите: docker compose up -d redis",
            exc,
        )
        return MemoryStorage()


async def create_dispatcher(settings: Settings) -> Dispatcher:
    storage = await build_fsm_storage(settings)
    dp = Dispatcher(storage=storage)

    dp.update.outer_middleware(UpdateLoggingMiddleware())
    dp.update.middleware(DbSessionMiddleware(get_session_factory()))

    @dp.errors()
    async def on_error(event: object) -> None:
        logger.exception("Telegram handler error: %r", event)

    dp.include_router(start.router)
    dp.include_router(places.router)
    dp.include_router(onboarding.router)
    dp.include_router(menu.router)
    return dp


async def send_text_to_user(telegram_id: int, text: str, settings: Settings) -> None:
    bot = create_bot(settings)
    try:
        await bot.send_message(telegram_id, text)
    finally:
        await bot.session.close()
