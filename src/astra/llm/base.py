"""Базовый контракт LLM-провайдеров."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import httpx

from astra.llm.types import CompletionRequest, CompletionResult

logger = logging.getLogger(__name__)


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
        if isinstance(exc, httpx.TimeoutException):
            logger.warning("%s request timed out", log_label)
            return "timeout"
        if isinstance(exc, httpx.ConnectError):
            logger.warning("%s connection failed", log_label)
            return "connection"
        if isinstance(exc, httpx.HTTPStatusError):
            response = exc.response
            detail = BaseLlmProvider._http_error_detail(response)
            if detail:
                logger.warning(
                    "%s HTTP error %s: %s",
                    log_label,
                    response.status_code,
                    detail,
                )
                return f"http_{response.status_code}:{detail}"
            logger.warning("%s HTTP error: %s", log_label, response.status_code)
            return f"http_{response.status_code}"
        logger.exception("%s request failed", log_label)
        return "request_error"
