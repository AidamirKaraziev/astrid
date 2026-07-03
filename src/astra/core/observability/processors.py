"""Structlog processors: service tag, PII sanitization, type serialization."""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

_SENSITIVE_KEY_RE = re.compile(
    r"(token|secret|password|api[_-]?key|authorization|prompt|completion|message_text)",
    re.IGNORECASE,
)
_MASK = "***"


def add_service(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    from astra.core.observability.context import service_var

    service = service_var.get()
    if service and "service" not in event_dict:
        event_dict["service"] = service
    return event_dict


def add_context_fields(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    from astra.core.observability.context import context_as_dict

    for key, value in context_as_dict().items():
        event_dict.setdefault(key, value)
    return event_dict


def _should_mask_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY_RE.search(key))


def _sanitize_value(key: str, value: Any) -> Any:
    if _should_mask_key(key):
        return _MASK
    if isinstance(value, dict):
        return {k: _sanitize_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(key, item) for item in value]
    return value


def add_trace_context(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            event_dict.setdefault("trace_id", format(ctx.trace_id, "032x"))
            event_dict.setdefault("span_id", format(ctx.span_id, "016x"))
    except Exception:
        pass
    return event_dict


def serialize_types(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    for key, value in list(event_dict.items()):
        if isinstance(value, UUID):
            event_dict[key] = str(value)
        elif isinstance(value, (datetime, date)):
            event_dict[key] = value.isoformat()
        elif isinstance(value, Enum):
            event_dict[key] = str(value.value)
    return event_dict


def sanitize_pii(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    return {key: _sanitize_value(key, value) for key, value in event_dict.items()}
