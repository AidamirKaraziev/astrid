"""Обёртка LLM-провайдера: structured logs + OTel span на каждый complete()."""

from __future__ import annotations

import time

from astra.core.observability import Event, get_logger
from astra.core.observability.tracing import start_span
from astra.llm.accounting import record_call
from astra.llm.base import BaseLlmProvider
from astra.llm.types import CompletionRequest, CompletionResult

log = get_logger(__name__)


class TracingLlmProvider(BaseLlmProvider):
    def __init__(self, inner: BaseLlmProvider, *, purpose: str = "unknown") -> None:
        self._inner = inner
        self._purpose = purpose

    @property
    def name(self) -> str:
        return self._inner.name

    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        with start_span(
            "llm.complete",
            provider=self.name,
            purpose=self._purpose,
        ) as span:
            started = time.perf_counter()
            log.info(Event.LLM_REQUEST, provider=self.name, purpose=self._purpose)
            result = await self._inner.complete(request)
            duration_ms = round((time.perf_counter() - started) * 1000)
            status = "ok" if result.text and not result.reason else "fail"
            log.info(
                Event.LLM_RESPONSE,
                provider=self.name,
                purpose=self._purpose,
                duration_ms=duration_ms,
                status=status,
                reason=result.reason or None,
            )
            if span is not None:
                span.set_attribute("llm.provider", self.name)
                span.set_attribute("llm.purpose", self._purpose)
                span.set_attribute("llm.status", status)
                span.set_attribute("llm.duration_ms", duration_ms)
                if result.reason:
                    span.set_attribute("llm.reason", result.reason)
                if result.usage.known:
                    span.set_attribute("llm.prompt_tokens", result.usage.prompt or 0)
                    span.set_attribute("llm.completion_tokens", result.usage.completion or 0)

            await record_call(
                provider=self.name,
                model=result.model,
                purpose=self._purpose,
                status=status,
                reason=result.reason,
                duration_ms=duration_ms,
                usage=result.usage,
            )
            return result
