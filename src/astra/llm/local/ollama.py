"""Клиент Ollama — self-hosted LLM."""

from __future__ import annotations

import httpx

from astra.core.config import Settings, get_settings
from astra.llm.base import BaseLlmProvider
from astra.llm.types import CompletionRequest, CompletionResult


class OllamaProvider(BaseLlmProvider):
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def settings(self) -> Settings:
        return self._settings

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        cfg = self._settings
        options: dict[str, object] = {}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens

        extra = request.extra
        if "num_ctx" in extra:
            options["num_ctx"] = extra["num_ctx"]
        if "keep_alive" in extra:
            keep_alive = extra["keep_alive"]
        else:
            keep_alive = "30m"

        think = extra.get("think", False)

        payload: dict[str, object] = {
            "model": cfg.ollama_model,
            "think": think,
            "keep_alive": keep_alive,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "stream": False,
        }
        if options:
            payload["options"] = options

        url = f"{cfg.ollama_base_url.rstrip('/')}/api/chat"
        timeout = request.timeout_seconds or cfg.ollama_timeout_seconds
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            return CompletionResult(None, self.map_http_error(exc, log_label="Ollama"))

        message = data.get("message") or {}
        raw = (message.get("content") or "").strip()
        if not raw:
            return CompletionResult(None, "empty_response")
        return CompletionResult(raw)
