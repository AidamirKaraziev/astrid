import asyncio
import logging

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from astra.core.config import Settings, get_settings
from astra.db.session import get_session_factory, init_engine
from astra.messaging.publisher import _ensure_topology, parse_task
from astra.messaging.queues import QUEUE_ASTRO, QUEUE_NOTIFICATIONS, QUEUE_PREDICTIONS
from astra.workers.handlers import dispatch_task

logger = logging.getLogger(__name__)


async def _process_message(message: AbstractIncomingMessage) -> None:
    async with message.process(requeue=True):
        task = parse_task(message.body)
        factory = get_session_factory()
        async with factory() as session:
            await dispatch_task(session, task)
            await session.commit()


async def run_consumer(settings: Settings | None = None) -> None:
    cfg = settings or get_settings()
    init_engine(cfg)
    connection = await aio_pika.connect_robust(cfg.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=cfg.rabbitmq_prefetch)

    await _ensure_topology(channel)
    queues = []
    for name in (QUEUE_ASTRO, QUEUE_PREDICTIONS, QUEUE_NOTIFICATIONS):
        queue = await channel.declare_queue(name, durable=True)
        queues.append(queue)

    logger.info("Worker listening on %s", ", ".join(q.name for q in queues))

    for queue in queues:
        await queue.consume(_process_message)

    try:
        await asyncio.Future()
    finally:
        await connection.close()
