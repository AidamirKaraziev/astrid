import json
import logging
from datetime import date
from uuid import UUID

import aio_pika

from astra.core.config import Settings, get_settings
from astra.messaging.queues import (
    EXCHANGE_NAME,
    QUEUE_ASTRO,
    QUEUE_NOTIFICATIONS,
    QUEUE_PREDICTIONS,
    ROUTING_NATAL_CHART,
    ROUTING_PREDICTION_GENERATE,
    ROUTING_PREDICTION_SEND,
)
from astra.messaging.schemas import TaskMessage, TaskType

logger = logging.getLogger(__name__)

_connection: aio_pika.RobustConnection | None = None
_channel: aio_pika.Channel | None = None
_exchange: aio_pika.Exchange | None = None


async def _ensure_topology(channel: aio_pika.Channel) -> aio_pika.Exchange:
    global _exchange
    if _exchange is not None:
        return _exchange
    exchange = await channel.declare_exchange(
        EXCHANGE_NAME,
        aio_pika.ExchangeType.DIRECT,
        durable=True,
    )
    bindings = (
        (QUEUE_ASTRO, ROUTING_NATAL_CHART),
        (QUEUE_PREDICTIONS, ROUTING_PREDICTION_GENERATE),
        (QUEUE_NOTIFICATIONS, ROUTING_PREDICTION_SEND),
    )
    for queue_name, routing_key in bindings:
        queue = await channel.declare_queue(queue_name, durable=True)
        await queue.bind(exchange, routing_key=routing_key)
    _exchange = exchange
    return exchange


async def _get_channel(settings: Settings | None = None) -> tuple[aio_pika.Channel, aio_pika.Exchange]:
    global _connection, _channel
    cfg = settings or get_settings()
    if _channel is None or _channel.is_closed:
        _connection = await aio_pika.connect_robust(cfg.rabbitmq_url)
        _channel = await _connection.channel()
    exchange = await _ensure_topology(_channel)
    return _channel, exchange


async def close_publisher() -> None:
    global _connection, _channel, _exchange
    if _connection and not _connection.is_closed:
        await _connection.close()
    _connection = None
    _channel = None
    _exchange = None


async def _publish(
    routing_key: str,
    message: TaskMessage,
    settings: Settings | None = None,
) -> None:
    cfg = settings or get_settings()
    if not cfg.rabbitmq_enabled:
        return
    _, exchange = await _get_channel(cfg)
    body = message.model_dump_json().encode("utf-8")
    await exchange.publish(
        aio_pika.Message(
            body=body,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
        ),
        routing_key=routing_key,
    )
    logger.debug("Published %s for user %s", message.type, message.user_id)


async def publish_natal_chart(user_id: UUID, settings: Settings | None = None) -> None:
    await _publish(
        ROUTING_NATAL_CHART,
        TaskMessage(type=TaskType.NATAL_CHART_GENERATE, user_id=user_id),
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


def parse_task(body: bytes) -> TaskMessage:
    return TaskMessage.model_validate(json.loads(body))
