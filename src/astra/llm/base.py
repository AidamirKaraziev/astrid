"""Базовый контракт LLM-провайдеров."""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from astra.core.observability import Event, get_logger
from astra.llm.types import CompletionRequest, CompletionResult

log = get_logger(__name__)


class BaseLlmProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Идентификатор провайдера: ollama, grok, …"""

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResult:
        """Сгенерировать ответ; reason пустой при успехе."""

    @staticmethod
    def _http_error_detail(response: httpx.Response) -> str:
        try:
            data = response.json()
        except Exception:
            text = (response.text or "").strip()
            return text[:300] if text else ""

        if not isinstance(data, dict):
            return ""

        error = data.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("code")
            return str(message) if message else ""
        if isinstance(error, str):
            return error

        for key in ("message", "detail", "error_description"):
            value = data.get(key)
            if value:
                return str(value)
        return ""

    @staticmethod
    def map_http_error(exc: Exception, *, log_label: str) -> str:
        provider = log_label
        if isinstance(exc, httpx.TimeoutException):
            log.warning(Event.LLM_HTTP_ERROR, provider=provider, reason="timeout")
            return "timeout"
        if isinstance(exc, httpx.ConnectError):
            log.warning(Event.LLM_HTTP_ERROR, provider=provider, reason="connection")
            return "connection"
        if isinstance(exc, httpx.HTTPStatusError):
            response = exc.response
            detail = BaseLlmProvider._http_error_detail(response)
            if detail:
                log.warning(
                    Event.LLM_HTTP_ERROR,
                    provider=provider,
                    status_code=response.status_code,
                    reason=detail,
                )
                return f"http_{response.status_code}:{detail}"
            log.warning(
                Event.LLM_HTTP_ERROR,
                provider=provider,
                status_code=response.status_code,
            )
            return f"http_{response.status_code}"
        log.exception(Event.LLM_HTTP_ERROR, provider=provider, reason="request_error")
        return "request_error"
