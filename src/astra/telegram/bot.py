from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import ErrorEvent
from redis.asyncio import Redis

from astra.core.config import Settings
from astra.core.observability import get_logger
from astra.core.observability.middleware.telegram import TelegramObservabilityMiddleware
from astra.db.session import get_session_factory
from astra.telegram.auto_keyboard_middleware import AutoKeyboardMiddleware
from astra.telegram.bot_menu import setup_bot_menu
from astra.telegram.handlers import catalog, commands, compatibility, menu, natal, onboarding, people, places, start, tarot_daily
from astra.telegram.middlewares import DbSessionMiddleware

log = get_logger(__name__)


def create_bot(settings: Settings) -> Bot:
    proxy = settings.telegram_proxy_url_effective
    if proxy:
        session = AiohttpSession(proxy=proxy)
        log.info("telegram.bot_api.proxy", use_vpn=True)
    else:
        session = AiohttpSession()
        log.info("telegram.bot_api.direct", use_vpn=False)
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )


async def build_fsm_storage(settings: Settings) -> BaseStorage:
    """Redis для FSM; если недоступен — MemoryStorage (dev без docker)."""
    if settings.fsm_storage == "memory":
        log.info("telegram.fsm.memory", configured=True)
        return MemoryStorage()

    try:
        redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        await redis.ping()
        log.info("telegram.fsm.redis")
        return RedisStorage(redis=redis)
    except Exception as exc:
        log.warning(
            "telegram.fsm.fallback_memory",
            error_type=type(exc).__name__,
            hint="docker compose up -d redis",
        )
        return MemoryStorage()


async def create_dispatcher(settings: Settings) -> Dispatcher:
    storage = await build_fsm_storage(settings)
    dp = Dispatcher(storage=storage)

    dp.update.outer_middleware(TelegramObservabilityMiddleware())
    dp.update.middleware(DbSessionMiddleware(get_session_factory()))
    dp.message.middleware(AutoKeyboardMiddleware())
    dp.callback_query.middleware(AutoKeyboardMiddleware())

    @dp.errors()
    async def on_error(event: ErrorEvent) -> None:
        from astra.core.sentry import capture_exception

        log.exception("telegram.handler.error", exc_info=event.exception)
        capture_exception(event.exception)

    dp.include_router(start.router)
    dp.include_router(commands.router)
    dp.include_router(places.router)
    dp.include_router(onboarding.router)
    dp.include_router(menu.router)
    dp.include_router(compatibility.router)
    dp.include_router(people.router)
    dp.include_router(natal.router)
    dp.include_router(tarot_daily.router)
    dp.include_router(catalog.router)

    # AI-чат Astrid — регистрируется ПОСЛЕДНИМ, чтобы кнопки/FSM ловились раньше.
    if settings.ai_chat_enabled:
        from astra.telegram.ai_chat import router as ai_chat_router

        dp.include_router(ai_chat_router)
        log.info("telegram.ai_chat.enabled", provider=settings.ai_chat_provider)

    return dp


async def send_text_to_user(telegram_id: int, text: str, settings: Settings) -> None:
    from astra.workers.telegram_send import send_prediction_to_telegram

    await send_prediction_to_telegram(telegram_id, text, settings=settings)


async def configure_telegram_bot(bot: Bot) -> None:
    """Menu Button, команды и прочая настройка Bot API при старте."""
    if not bot.token:
        return
    await setup_bot_menu(bot)
