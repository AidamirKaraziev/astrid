"""Контекст запроса/задачи через contextvars — автоподмешивание в логи."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any
from uuid import UUID, uuid4

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
user_id_var: ContextVar[UUID | None] = ContextVar("user_id", default=None)
report_id_var: ContextVar[UUID | None] = ContextVar("report_id", default=None)
task_type_var: ContextVar[str | None] = ContextVar("task_type", default=None)
service_var: ContextVar[str | None] = ContextVar("service", default=None)

_CONTEXT_VARS: dict[str, ContextVar[Any]] = {
    "correlation_id": correlation_id_var,
    "user_id": user_id_var,
    "report_id": report_id_var,
    "task_type": task_type_var,
    "service": service_var,
}


def new_correlation_id(prefix: str = "cid") -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def get_correlation_id() -> str | None:
    return correlation_id_var.get()


def ensure_correlation_id(prefix: str = "cid") -> str:
    current = correlation_id_var.get()
    if current:
        return current
    new_id = new_correlation_id(prefix)
    correlation_id_var.set(new_id)
    return new_id


def bind_context(**kwargs: Any) -> dict[str, Token[Any]]:
    """Установить поля контекста; вернуть токены для отката."""
    tokens: dict[str, Token[Any]] = {}
    for key, value in kwargs.items():
        var = _CONTEXT_VARS.get(key)
        if var is None:
            continue
        if value is not None:
            tokens[key] = var.set(value)
    return tokens


def reset_context(tokens: dict[str, Token[Any]]) -> None:
    for key, token in tokens.items():
        var = _CONTEXT_VARS.get(key)
        if var is not None:
            var.reset(token)


@contextmanager
def bound_context(**kwargs: Any):
    tokens = bind_context(**kwargs)
    try:
        yield
    finally:
        reset_context(tokens)


def context_as_dict() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, var in _CONTEXT_VARS.items():
        value = var.get()
        if value is not None:
            result[key] = value
    return result
