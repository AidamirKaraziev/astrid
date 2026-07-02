import json
import logging
from datetime import date
from uuid import UUID

import aio_pika
import aiormq

from astra.core.config import Settings, get_settings
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
    ROUTING_PDF_GENERATE,
    ROUTING_PREDICTION_GENERATE,
    ROUTING_PREDICTION_SEND,
    ROUTING_SYNASTRY_BUILD,
)
from astra.messaging.schemas import TaskMessage, TaskType

logger = logging.getLogger(__name__)

_connection: aio_pika.RobustConnection | None = None
_channel: aio_pika.Channel | None = None
_exchange: aio_pika.Exchange | None = None


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
    body = message.model_dump_json().encode("utf-8")
    payload = aio_pika.Message(
        body=body,
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        content_type="application/json",
    )
    for attempt in range(2):
        _, exchange = await _get_channel(cfg)
        try:
            await exchange.publish(payload, routing_key=routing_key)
            logger.debug("Published %s for user %s", message.type, message.user_id)
            return
        except aiormq.exceptions.ChannelInvalidStateError:
            if attempt == 0:
                logger.warning("RabbitMQ channel closed, reconnecting and retrying publish")
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
        TaskMessage(
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
        TaskMessage(
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
        TaskMessage(
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
        TaskMessage(
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
        TaskMessage(type=TaskType.SYNASTRY_BUILD, report_id=report_id),
        settings,
    )


async def publish_compatibility_generate(
    report_id: UUID,
    settings: Settings | None = None,
) -> None:
    await _publish(
        ROUTING_COMPATIBILITY_GENERATE,
        TaskMessage(type=TaskType.COMPATIBILITY_GENERATE, report_id=report_id),
        settings,
    )


async def publish_pdf_generate(
    report_id: UUID,
    settings: Settings | None = None,
) -> None:
    await _publish(
        ROUTING_PDF_GENERATE,
        TaskMessage(type=TaskType.PDF_GENERATE, report_id=report_id),
        settings,
    )


async def publish_compatibility_send(
    report_id: UUID,
    settings: Settings | None = None,
) -> None:
    await _publish(
        ROUTING_COMPATIBILITY_SEND,
        TaskMessage(type=TaskType.COMPATIBILITY_SEND, report_id=report_id),
        settings,
    )


def parse_task(body: bytes) -> TaskMessage:
    return TaskMessage.model_validate(json.loads(body))
