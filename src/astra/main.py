import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from astra.core.config import get_settings
from astra.db.session import init_engine
from astra.notifications.scheduler import notification_worker
from astra.predictions.routers import router as predictions_router
from astra.points.routers import router as points_router
from astra.referrals.routers import router as referrals_router
from astra.telegram.bot import create_bot, create_dispatcher, send_text_to_user
from astra.telegram.webapp_router import router as telegram_webapp_router
from astra.telegram.webhook import router as telegram_webhook_router
from astra.users.routers import router as users_router

logger = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_logging(settings.log_level)
    init_engine(settings)

    bot = create_bot(settings)
    dp = await create_dispatcher(settings)
    app.state.bot = bot
    app.state.dp = dp

    async def bot_send_text(telegram_id: int, text: str) -> None:
        await bot.send_message(telegram_id, text)

    worker_task = asyncio.create_task(
        notification_worker(bot_send_text, settings=settings),
        name="notification_worker",
    )

    polling_task: asyncio.Task | None = None
    if settings.telegram_mode == "polling":
        polling_task = asyncio.create_task(
            dp.start_polling(bot, handle_signals=False),
            name="telegram_polling",
        )
        logger.info("Telegram bot started in polling mode")
    elif settings.telegram_webhook_url:
        await bot.set_webhook(
            url=settings.telegram_webhook_url,
            secret_token=settings.telegram_webhook_secret,
        )
        logger.info("Telegram webhook registered: %s", settings.telegram_webhook_url)

    yield

    worker_task.cancel()
    if polling_task:
        polling_task.cancel()
    tasks = [worker_task]
    if polling_task:
        tasks.append(polling_task)
    for task in tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
    await bot.session.close()


def create_app(*, with_lifespan: bool = True) -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Astra API",
        version="0.1.0",
        description="Персональные предсказания — API для Telegram и будущих клиентов",
        lifespan=lifespan if with_lifespan else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_development else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(users_router, prefix="/v1")
    app.include_router(predictions_router, prefix="/v1")
    app.include_router(points_router, prefix="/v1")
    app.include_router(referrals_router, prefix="/v1")
    app.include_router(telegram_webhook_router, prefix="/v1")
    app.include_router(telegram_webapp_router)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "astra.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
        app_dir="src",
    )


if __name__ == "__main__":
    run()
