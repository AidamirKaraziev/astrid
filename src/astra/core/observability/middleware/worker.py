"""Worker middleware: lifecycle логов для RabbitMQ задач."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from aio_pika.abc import AbstractIncomingMessage

from astra.core.observability.context import bound_context, new_correlation_id
from astra.core.observability.events import Event
from astra.core.observability.logging import get_logger
from astra.core.observability.tracing import (
    detach_trace_context,
    extract_trace_context,
    start_span,
)
from astra.messaging.schemas import TaskMessage

log = get_logger(__name__)

_CORRELATION_HEADER = "x-correlation-id"


def _correlation_id_from_message(
    message: AbstractIncomingMessage,
    task: TaskMessage,
) -> str:
    if task.correlation_id:
        return task.correlation_id
    headers = message.headers or {}
    if isinstance(headers, dict):
        raw = headers.get(_CORRELATION_HEADER)
        if raw is not None:
            return str(raw)
    return new_correlation_id("msg")


async def run_task_with_observability(
    message: AbstractIncomingMessage,
    task: TaskMessage,
    handler: Callable[[], Awaitable[None]],
    *,
    queue_name: str | None = None,
) -> None:
    correlation_id = _correlation_id_from_message(message, task)
    queue = queue_name or message.routing_key or "unknown"
    headers = message.headers if isinstance(message.headers, dict) else {}
    trace_token = extract_trace_context(headers)

    try:
        with bound_context(
            correlation_id=correlation_id,
            user_id=task.user_id,
            report_id=task.report_id,
            task_type=str(task.type),
        ):
            with start_span(
                "worker.task",
                task_type=str(task.type),
                queue=queue,
            ):
                started = time.perf_counter()
                log.info(
                    Event.TASK_RECEIVED,
                    queue=queue,
                    message_id=message.message_id,
                    retry=task.retry,
                )
                try:
                    await handler()
                    duration_ms = round((time.perf_counter() - started) * 1000)
                    log.info(Event.TASK_COMPLETED, duration_ms=duration_ms)
                except Exception as exc:
                    duration_ms = round((time.perf_counter() - started) * 1000)
                    log.exception(
                        Event.TASK_FAILED,
                        duration_ms=duration_ms,
                        error_type=type(exc).__name__,
                    )
                    raise
    finally:
        detach_trace_context(trace_token)
