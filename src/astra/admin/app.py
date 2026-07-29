"""Панель как самостоятельное приложение.

Сейчас она едет внутри `api` (одна строка `include_router` в `astra.main`), но
собрана так, чтобы переезд в отдельный сервис стоил ровно двух правок: убрать
ту строку и поднять контейнер с `astra-admin` из того же образа. Адреса при
этом не меняются — префикс `/admin` живёт в самом роутере, так что закладка в
браузере переживёт переезд.

Что нельзя тащить в панель, чтобы шов не зарос:

* **никакого `app.state.bot` и вообще aiogram** — в отдельном процессе бота не
  будет. Всё, что нужно от Telegram, зовём напрямую через Bot API
  (`refund_star_payment_api` умеет так) или кладём задачу в RabbitMQ;
* **никаких импортов из `astra.telegram`** — иначе отдельный сервис потащит за
  собой хендлеры и клавиатуры;
* **ничего тяжёлого в самом запросе** — агрегаты и рассылки уводим в воркер,
  панель ставит задачу и показывает статус.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from astra.core.config import get_settings
from astra.core.observability import configure_observability, get_logger
from astra.core.observability.middleware.http import HttpObservabilityMiddleware
from astra.core.sentry import init_sentry
from astra.db.session import get_engine, init_engine

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Панели нужна только база: ни бота, ни очередей, ни планировщика."""
    settings = get_settings()
    init_engine(settings)
    log.info("admin.app.started")
    yield
    await get_engine().dispose()
    log.info("admin.app.shutdown")


def create_admin_app(*, with_lifespan: bool = True) -> FastAPI:
    from astra.admin.routers import router as admin_router

    settings = get_settings()
    configure_observability(settings)
    init_sentry(settings)
    app = FastAPI(
        title="Astra Admin",
        version="0.1.0",
        description="Панель управления каталогом и заказами",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan if with_lifespan else None,
    )
    app.add_middleware(HttpObservabilityMiddleware)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(admin_router)
    return app


app = create_admin_app()


def run() -> None:
    import uvicorn

    uvicorn.run(app="astra.admin.app:app", host="0.0.0.0", port=8001, app_dir="src")


if __name__ == "__main__":
    run()
