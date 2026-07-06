import json
from datetime import date
from uuid import UUID

import aio_pika
import aiormq

from astra.core.config import Settings, get_settings
from astra.core.observability import Event, ensure_correlation_id, get_correlation_id, get_logger
from astra.core.observability.tracing import inject_trace_context
from astra.messaging.queues import (
    EXCHANGE_NAME,
    QUEUE_ASTRO,
    QUEUE_COMPATIBILITY,
    QUEUE_NOTIFICATIONS,
    QUEUE_PREDICTIONS,
    QUEUE_REPORTS,
    ROUTING_COMPATIBILITY_GENERATE,
    ROUTING_COMPATIBILITY_SEND,
    ROUTING_DAILY_CONTEXT_BUILD,
    ROUTING_NATAL_CHART,
    ROUTING_NATAL_GENERATE,
    ROUTING_NATAL_PDF_GENERATE,
    ROUTING_NATAL_SEND,
    ROUTING_PDF_GENERATE,
    ROUTING_PREDICTION_GENERATE,
    ROUTING_PREDICTION_SEND,
    ROUTING_SYNASTRY_BUILD,
)
from astra.messaging.schemas import TaskMessage, TaskType

log = get_logger(__name__)

_CORRELATION_HEADER = "x-correlation-id"

_connection: aio_pika.RobustConnection | None = None
_channel: aio_pika.Channel | None = None
_exchange: aio_pika.Exchange | None = None


def _task_message(**kwargs) -> TaskMessage:
    correlation_id = (
        kwargs.pop("correlation_id", None)
        or get_correlation_id()
        or ensure_correlation_id("task")
    )
    return TaskMessage(correlation_id=correlation_id, **kwargs)


async def _ensure_topology(channel: aio_pika.Channel) -> aio_pika.Exchange:
    exchange = await channel.declare_exchange(
        EXCHANGE_NAME,
        aio_pika.ExchangeType.DIRECT,
        durable=True,
    )
    bindings = (
        (QUEUE_ASTRO, ROUTING_NATAL_CHART),
        (QUEUE_ASTRO, ROUTING_DAILY_CONTEXT_BUILD),
        (QUEUE_ASTRO, ROUTING_SYNASTRY_BUILD),
        (QUEUE_PREDICTIONS, ROUTING_PREDICTION_GENERATE),
        (QUEUE_NOTIFICATIONS, ROUTING_PREDICTION_SEND),
        (QUEUE_NOTIFICATIONS, ROUTING_COMPATIBILITY_SEND),
        (QUEUE_COMPATIBILITY, ROUTING_COMPATIBILITY_GENERATE),
        (QUEUE_REPORTS, ROUTING_PDF_GENERATE),
        (QUEUE_COMPATIBILITY, ROUTING_NATAL_GENERATE),
        (QUEUE_REPORTS, ROUTING_NATAL_PDF_GENERATE),
        (QUEUE_NOTIFICATIONS, ROUTING_NATAL_SEND),
    )
    for queue_name, routing_key in bindings:
        queue = await channel.declare_queue(queue_name, durable=True)
        await queue.bind(exchange, routing_key=routing_key)
    return exchange


async def _get_channel(settings: Settings | None = None) -> tuple[aio_pika.Channel, aio_pika.Exchange]:
    global _connection, _channel, _exchange
    cfg = settings or get_settings()
    if _channel is None or _channel.is_closed:
        if _connection is not None and not _connection.is_closed:
            await _connection.close()
        _connection = await aio_pika.connect_robust(cfg.rabbitmq_url)
        _channel = await _connection.channel()
        _exchange = None
    if _exchange is None or _exchange.channel.is_closed:
        _exchange = await _ensure_topology(_channel)
    return _channel, _exchange


async def close_publisher() -> None:
    global _connection, _channel, _exchange
    if _connection and not _connection.is_closed:
        await _connection.close()
    _connection = None
    _channel = None
    _exchange = None


async def verify_rabbitmq(settings: Settings | None = None) -> None:
    """Проверить подключение и топологию очередей при старте API/worker."""
    cfg = settings or get_settings()
    connection = await aio_pika.connect_robust(cfg.rabbitmq_url)
    try:
        channel = await connection.channel()
        await _ensure_topology(channel)
    finally:
        await connection.close()


async def _publish(
    routing_key: str,
    message: TaskMessage,
    settings: Settings | None = None,
) -> None:
    cfg = settings or get_settings()
    if not message.correlation_id:
        message = message.model_copy(
            update={"correlation_id": get_correlation_id() or ensure_correlation_id("task")},
        )
    body = message.model_dump_json().encode("utf-8")
    headers: dict[str, str] = {_CORRELATION_HEADER: message.correlation_id or ""}
    inject_trace_context(headers)
    payload = aio_pika.Message(
        body=body,
        headers=headers,
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        content_type="application/json",
    )
    for attempt in range(2):
        _, exchange = await _get_channel(cfg)
        try:
            await exchange.publish(payload, routing_key=routing_key)
            log.info(
                Event.TASK_PUBLISHED,
                task_type=str(message.type),
                routing_key=routing_key,
                user_id=message.user_id,
                report_id=message.report_id,
                correlation_id=message.correlation_id,
            )
            return
        except aiormq.exceptions.ChannelInvalidStateError:
            if attempt == 0:
                log.warning(Event.RABBITMQ_RECONNECT, routing_key=routing_key)
                await close_publisher()
                continue
            raise


async def publish_natal_chart(
    user_id: UUID,
    prediction_date: date,
    settings: Settings | None = None,
) -> None:
    await _publish(
        ROUTING_NATAL_CHART,
    ROUTING_NATAL_GENERATE,
    ROUTING_NATAL_PDF_GENERATE,
    ROUTING_NATAL_SEND,
        _task_message(
            type=TaskType.NATAL_CHART_GENERATE,
            user_id=user_id,
            prediction_date=prediction_date,
        ),
        settings,
    )


async def publish_daily_context_build(
    user_id: UUID,
    prediction_date: date,
    settings: Settings | None = None,
) -> None:
    await _publish(
        ROUTING_DAILY_CONTEXT_BUILD,
        _task_message(
            type=TaskType.DAILY_CONTEXT_BUILD,
            user_id=user_id,
            prediction_date=prediction_date,
        ),
        settings,
    )


async def publish_prediction_generate(
    user_id: UUID,
    prediction_date: date | None = None,
    settings: Settings | None = None,
) -> None:
    await _publish(
        ROUTING_PREDICTION_GENERATE,
        _task_message(
            type=TaskType.PREDICTION_GENERATE,
            user_id=user_id,
            prediction_date=prediction_date,
        ),
        settings,
    )


async def publish_prediction_send(
    user_id: UUID,
    prediction_date: date,
    settings: Settings | None = None,
) -> None:
    await _publish(
        ROUTING_PREDICTION_SEND,
        _task_message(
            type=TaskType.PREDICTION_SEND,
            user_id=user_id,
            prediction_date=prediction_date,
        ),
        settings,
    )


async def publish_synastry_build(
    report_id: UUID,
    settings: Settings | None = None,
) -> None:
    await _publish(
        ROUTING_SYNASTRY_BUILD,
        _task_message(type=TaskType.SYNASTRY_BUILD, report_id=report_id),
        settings,
    )


async def publish_compatibility_generate(
    report_id: UUID,
    settings: Settings | None = None,
) -> None:
    await _publish(
        ROUTING_COMPATIBILITY_GENERATE,
        _task_message(type=TaskType.COMPATIBILITY_GENERATE, report_id=report_id),
        settings,
    )


async def publish_pdf_generate(
    report_id: UUID,
    settings: Settings | None = None,
) -> None:
    await _publish(
        ROUTING_PDF_GENERATE,
        _task_message(type=TaskType.PDF_GENERATE, report_id=report_id),
        settings,
    )


async def publish_compatibility_send(
    report_id: UUID,
    settings: Settings | None = None,
) -> None:
    await _publish(
        ROUTING_COMPATIBILITY_SEND,
        _task_message(type=TaskType.COMPATIBILITY_SEND, report_id=report_id),
        settings,
    )


async def publish_natal_generate(
    report_id: UUID,
    settings: Settings | None = None,
) -> None:
    await _publish(
        ROUTING_NATAL_GENERATE,
        _task_message(type=TaskType.NATAL_GENERATE, report_id=report_id),
        settings,
    )


async def publish_natal_pdf_generate(
    report_id: UUID,
    settings: Settings | None = None,
) -> None:
    await _publish(
        ROUTING_NATAL_PDF_GENERATE,
        _task_message(type=TaskType.NATAL_PDF_GENERATE, report_id=report_id),
        settings,
    )


async def publish_natal_send(
    report_id: UUID,
    settings: Settings | None = None,
) -> None:
    await _publish(
        ROUTING_NATAL_SEND,
        _task_message(type=TaskType.NATAL_SEND, report_id=report_id),
        settings,
    )


def parse_task(body: bytes) -> TaskMessage:
    return TaskMessage.model_validate(json.loads(body))
