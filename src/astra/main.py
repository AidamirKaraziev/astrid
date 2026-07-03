import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from astra.core.config import get_settings
from astra.core.observability import Event, configure_observability, get_logger
from astra.core.observability.middleware.http import HttpObservabilityMiddleware
from astra.core.observability.tracing import instrument_fastapi_app, instrument_sqlalchemy_engine
from astra.core.sentry import init_sentry
from astra.db.session import get_session_factory, init_engine
from astra.places.geonames_import import ensure_places_catalog
from astra.messaging.publisher import close_publisher, verify_rabbitmq
from astra.notifications.scheduler import notification_worker
from astra.predictions.routers import router as predictions_router
from astra.points.routers import router as points_router
from astra.referrals.routers import router as referrals_router
from astra.telegram.bot import configure_telegram_bot, create_bot, create_dispatcher
from astra.workers.telegram_send import send_prediction_to_telegram
from astra.telegram.polling import run_polling_supervisor
from astra.telegram.webhook import router as telegram_webhook_router
from astra.users.routers import router as users_router

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_engine(settings)
    instrument_sqlalchemy_engine(settings)

    if settings.geonames_auto_import:
        try:
            ready = await ensure_places_catalog(get_session_factory())
            if ready:
                log.info("places.catalog.ready")
            else:
                log.warning("places.catalog.empty")
        except Exception:
            log.exception("places.catalog.import_failed")

    if not settings.telegram_bot_token:
        log.error(
            "telegram.bot_token.missing",
            hint="check .env TELEGRAM_BOT_TOKEN on server",
        )

    bot = create_bot(settings)
    notification_bot = create_bot(settings)
    dp = await create_dispatcher(settings)
    if settings.telegram_bot_token:
        try:
            await configure_telegram_bot(bot)
        except Exception:
            log.exception("telegram.bot_menu.configure_failed")

    try:
        await verify_rabbitmq(settings)
        log.info("rabbitmq.topology.verified")
    except Exception:
        log.exception(
            "rabbitmq.unavailable",
            hint="docker compose up -d rabbitmq worker",
        )

    app.state.bot = bot
    app.state.dp = dp

    async def bot_send_text(telegram_id: int, text: str) -> None:
        await send_prediction_to_telegram(telegram_id, text, settings=settings)

    worker_task = asyncio.create_task(
        notification_worker(bot_send_text, settings=settings),
        name="notification_worker",
    )

    polling_task: asyncio.Task | None = None
    if settings.telegram_mode == "polling":
        polling_task = asyncio.create_task(
            run_polling_supervisor(dp, bot),
            name="telegram_polling",
        )
        log.info(Event.APP_STARTED, component="telegram_polling")
    elif settings.telegram_webhook_url:
        await bot.delete_webhook(drop_pending_updates=False)
        await bot.set_webhook(
            url=settings.telegram_webhook_url,
            secret_token=settings.telegram_webhook_secret,
        )
        log.info("telegram.webhook.registered", url=settings.telegram_webhook_url)

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
    await notification_bot.session.close()
    await close_publisher()


def create_app(*, with_lifespan: bool = True) -> FastAPI:
    settings = get_settings()
    configure_observability(settings)
    init_sentry(settings)
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
    app.add_middleware(HttpObservabilityMiddleware)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(users_router, prefix="/v1")
    app.include_router(predictions_router, prefix="/v1")
    app.include_router(points_router, prefix="/v1")
    app.include_router(referrals_router, prefix="/v1")
    app.include_router(telegram_webhook_router, prefix="/v1")
    instrument_fastapi_app(settings, app)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        app="astra.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
        app_dir="src",
    )


if __name__ == "__main__":
    run()
