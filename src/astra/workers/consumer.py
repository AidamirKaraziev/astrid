import asyncio

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger
from astra.core.observability.middleware.worker import run_task_with_observability
from astra.db.session import get_session_factory, init_engine
from astra.llm.daily_llm import daily_provider_enabled
from astra.messaging.publisher import _ensure_topology, parse_task, republish_task
from astra.messaging.queues import (
    QUEUE_ASTRO,
    QUEUE_COMPATIBILITY,
    QUEUE_NOTIFICATIONS,
    QUEUE_PREDICTIONS,
    QUEUE_REPORTS,
)
from astra.core.observability.tracing import instrument_sqlalchemy_engine
from astra.users import crud as users_crud
from astra.messaging.schemas import TaskMessage
from astra.core.sentry import capture_exception
from astra.workers.handlers import dispatch_task, handle_task_dead
from astra.workers.telegram_send import BotBlockedError

log = get_logger(__name__)

# Сколько раз задачу можно повторить после первого сбоя. Первая попытка + 5 повторов;
# упавший повтор с retry == 5 — мёртвая задача. Без задержки между попытками:
# отложенная доставка требует DLX с TTL (отдельная работа).
MAX_TASK_RETRIES = 5


def check_daily_provider_configured(cfg: Settings) -> None:
    """Fail-loud при старте: без ключа DeepSeek daily-прогнозы уйдут в ретраи и FAILED."""
    if not daily_provider_enabled(cfg):
        log.warning(
            Event.LLM_DAILY_PROVIDER_UNCONFIGURED,
            hint="задай DEEPSEEK_ENABLED=true и DEEPSEEK_API_KEY в .env",
        )


async def _retry_or_bury(message: AbstractIncomingMessage, task: TaskMessage, exc: Exception) -> None:
    """Обработчик упал: копия с retry + 1 в ту же очередь либо, после лимита, мёртвая задача.

    Вернулась нормально — исходное сообщение подтвердится (ack). Если повтор не удалось
    оформить (RabbitMQ недоступен и т.п.), бросает исходную ошибку: старое поведение
    reject(requeue=True), сообщение не теряется.
    """
    try:
        if task.retry >= MAX_TASK_RETRIES:
            log.error(
                Event.TASK_DEAD,
                task_type=str(task.type),
                retry=task.retry,
                error_type=type(exc).__name__,
            )
            capture_exception(exc)
            async with get_session_factory()() as session:
                await handle_task_dead(session, task)
            return
        retried = await republish_task(message.routing_key or "", task)
    except Exception:
        log.exception(Event.TASK_FAILED, task_type=str(task.type), reason="retry_not_scheduled")
        raise exc from None
    log.warning(Event.TASK_FAILED, task_type=str(task.type), reason="retry_scheduled", retry=retried.retry)


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
                    # 403 — перманентно: помечаем пользователя, ack без повтора.
                    await session.rollback()
                    await users_crud.mark_bot_blocked(session, exc.telegram_id)
                    await session.commit()

        try:
            await run_task_with_observability(message, task, _run)
        except Exception as exc:
            # Порядок «копия, потом ack»: сбой между ними даст двойной запуск (обработчики
            # идемпотентны), обратный порядок потерял бы задачу.
            await _retry_or_bury(message, task, exc)


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
