"""Клиент xAI Grok API (OpenAI-совместимый chat completions)."""

from __future__ import annotations

import httpx

from astra.core.config import Settings, get_settings
from astra.llm.base import BaseLlmProvider
from astra.llm.types import CompletionRequest, CompletionResult


class GrokProvider(BaseLlmProvider):
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def name(self) -> str:
        return "grok"

    @property
    def settings(self) -> Settings:
        return self._settings

    def is_configured(self) -> bool:
        cfg = self._settings
        return cfg.grok_enabled and bool(cfg.xai_api_key.strip())

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        if not self.is_configured():
            return CompletionResult(None, "disabled")

        cfg = self._settings
        payload: dict[str, object] = {
            "model": cfg.grok_model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "stream": False,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        url = f"{cfg.grok_base_url.rstrip('/')}/chat/completions"
        timeout = request.timeout_seconds or cfg.grok_timeout_seconds
        headers = {"Authorization": f"Bearer {cfg.xai_api_key.strip()}"}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            return CompletionResult(None, self.map_http_error(exc, log_label="Grok"))

        choices = data.get("choices") or []
        if not choices:
            return CompletionResult(None, "empty_response")

        message = choices[0].get("message") or {}
        raw = (message.get("content") or "").strip()
        if not raw:
            return CompletionResult(None, "empty_response")
        return CompletionResult(raw)
