"""Structlog configuration — единая точка для api и worker."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

import structlog

from astra.core.observability.context import service_var
from astra.core.observability.processors import (
    add_context_fields,
    add_service,
    add_trace_context,
    sanitize_pii,
    serialize_types,
)
from astra.core.observability.tracing import configure_otel, instrument_httpx

if TYPE_CHECKING:
    from astra.core.config import Settings

_NOISY_LOGGERS = (
    "uvicorn.access",
    "uvicorn.error",
    "aiogram",
    "httpx",
    "httpcore",
    "sqlalchemy.engine",
    "aio_pika",
    "aiormq",
)

_CONFIGURED = False


def configure_observability(settings: Settings) -> None:
    """Настроить structured logging для процесса (идемпотентно)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    service = (settings.sentry_service or "api").strip().lower()
    service_var.set(service)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        add_service,
        add_context_fields,
        serialize_types,
        add_trace_context,
        sanitize_pii,
    ]

    if settings.log_format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    configure_otel(settings)
    instrument_httpx(settings)

    _CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
