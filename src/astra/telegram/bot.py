import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from astra.core.config import Settings
from astra.db.session import async_session_factory, init_engine
from astra.telegram.handlers import menu, onboarding, start
from astra.telegram.middlewares import DbSessionMiddleware

logger = logging.getLogger(__name__)


def create_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(settings: Settings) -> Dispatcher:
    redis = Redis.from_url(settings.redis_url)
    storage = RedisStorage(redis=redis)
    dp = Dispatcher(storage=storage)

    if async_session_factory is None:
        init_engine(settings)
    assert async_session_factory is not None
    dp.update.middleware(DbSessionMiddleware(async_session_factory))

    dp.include_router(start.router)
    dp.include_router(onboarding.router)
    dp.include_router(menu.router)
    return dp


async def send_text_to_user(telegram_id: int, text: str, settings: Settings) -> None:
    bot = create_bot(settings)
    try:
        await bot.send_message(telegram_id, text)
    finally:
        await bot.session.close()
