"""Контракт BaseLlmProvider: is_configured обязателен."""

from __future__ import annotations

import inspect

import pytest

from astra.llm.base import BaseLlmProvider
from astra.llm.tracing_provider import TracingLlmProvider
from astra.llm.types import CompletionRequest, CompletionResult


class _NoIsConfigured(BaseLlmProvider):
    @property
    def name(self) -> str:
        return "x"

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        raise NotImplementedError


class _Fake(_NoIsConfigured):
    def __init__(self, configured: bool) -> None:
        self._configured = configured

    def is_configured(self) -> bool:
        return self._configured


def test_is_configured_is_abstract() -> None:
    assert "is_configured" in BaseLlmProvider.__abstractmethods__


def test_subclass_without_is_configured_fails() -> None:
    with pytest.raises(TypeError, match="is_configured"):
        _NoIsConfigured()  # type: ignore[abstract]


@pytest.mark.parametrize("value", [True, False])
def test_tracing_delegates_is_configured(value: bool) -> None:
    assert TracingLlmProvider(_Fake(value)).is_configured() is value


def test_tracing_defines_is_configured_explicitly() -> None:
    assert "is_configured" in vars(TracingLlmProvider)
    assert not inspect.isabstract(TracingLlmProvider)
