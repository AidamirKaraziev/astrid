import asyncio

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger
from astra.core.observability.middleware.worker import run_task_with_observability
from astra.db.session import get_session_factory, init_engine
from astra.llm.daily_llm import daily_provider_enabled
from astra.messaging.publisher import _ensure_topology, parse_task
from astra.messaging.queues import (
    QUEUE_ASTRO,
    QUEUE_COMPATIBILITY,
    QUEUE_NOTIFICATIONS,
    QUEUE_PREDICTIONS,
    QUEUE_REPORTS,
)
from astra.core.observability.tracing import instrument_sqlalchemy_engine
from astra.users import crud as users_crud
from astra.workers.handlers import dispatch_task
from astra.workers.telegram_send import BotBlockedError

log = get_logger(__name__)


def check_daily_provider_configured(cfg: Settings) -> None:
    """Fail-loud при старте: без ключа DeepSeek daily-прогнозы уйдут в ретраи и FAILED."""
    if not daily_provider_enabled(cfg):
        log.warning(
            Event.LLM_DAILY_PROVIDER_UNCONFIGURED,
            hint="задай DEEPSEEK_ENABLED=true и DEEPSEEK_API_KEY в .env",
        )


async def _process_message(message: AbstractIncomingMessage) -> None:
    async with message.process(requeue=True):
        task = parse_task(message.body)
        factory = get_session_factory()

        async def _run() -> None:
            async with factory() as session:
                try:
                    await dispatch_task(session, task)
                    await session.commit()
                except BotBlockedError as exc:
                    # 403 — перманентно: помечаем пользователя, ack без requeue.
                    await session.rollback()
                    await users_crud.mark_bot_blocked(session, exc.telegram_id)
                    await session.commit()

        await run_task_with_observability(message, task, _run)


async def run_consumer(settings: Settings | None = None) -> None:
    cfg = settings or get_settings()
    init_engine(cfg)
    instrument_sqlalchemy_engine(cfg)
    check_daily_provider_configured(cfg)
    connection = await aio_pika.connect_robust(cfg.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=cfg.rabbitmq_prefetch)

    await _ensure_topology(channel)
    queues = []
    for name in (QUEUE_ASTRO, QUEUE_PREDICTIONS, QUEUE_NOTIFICATIONS, QUEUE_COMPATIBILITY, QUEUE_REPORTS):
        queue = await channel.declare_queue(name, durable=True)
        queues.append(queue)

    log.info(Event.APP_STARTED, queues=[q.name for q in queues])

    for queue in queues:
        await queue.consume(_process_message)

    try:
        await asyncio.Future()
    finally:
        await connection.close()
        log.info(Event.APP_SHUTDOWN)
