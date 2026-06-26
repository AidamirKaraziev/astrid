"""Клиент OpenRouter API (OpenAI-compatible chat completions)."""

from __future__ import annotations

import httpx

from astra.core.config import Settings, get_settings
from astra.llm.base import BaseLlmProvider
from astra.llm.types import CompletionRequest, CompletionResult


def _extract_message_text(message: dict[str, object]) -> str:
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()

    reasoning = message.get("reasoning")
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning.strip()

    return ""


class OpenRouterProvider(BaseLlmProvider):
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @staticmethod
    def _parse_fallback_models(raw: str) -> list[str]:
        return [item.strip() for item in raw.split(",") if item.strip()]

    def _payload_models(self, cfg: Settings) -> list[str] | None:
        fallbacks = self._parse_fallback_models(cfg.openrouter_fallback_models)
        if not fallbacks:
            return None
        primary = cfg.openrouter_model.strip()
        unique: list[str] = []
        for model_id in (primary, *fallbacks):
            if model_id and model_id not in unique:
                unique.append(model_id)
        if len(unique) <= 1:
            return None
        return unique[1:]

    @property
    def name(self) -> str:
        return "openrouter"

    @property
    def settings(self) -> Settings:
        return self._settings

    def is_configured(self) -> bool:
        cfg = self._settings
        return cfg.openrouter_enabled and bool(cfg.openrouter_api_key.strip())

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        if not self.is_configured():
            return CompletionResult(None, "disabled")

        cfg = self._settings
        payload: dict[str, object] = {
            "model": cfg.openrouter_model,
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

        fallback_models = self._payload_models(cfg)
        if fallback_models:
            payload["models"] = fallback_models

        url = f"{cfg.openrouter_base_url.rstrip('/')}/chat/completions"
        timeout = request.timeout_seconds or cfg.openrouter_timeout_seconds
        headers = {
            "Authorization": f"Bearer {cfg.openrouter_api_key.strip()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/astra-bot",
            "X-OpenRouter-Title": "Astra",
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            return CompletionResult(None, self.map_http_error(exc, log_label="OpenRouter"))

        choices = data.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            return CompletionResult(None, "empty_response")

        message = choices[0].get("message") or {}
        if not isinstance(message, dict):
            return CompletionResult(None, "empty_response")

        raw = _extract_message_text(message)
        if not raw:
            return CompletionResult(None, "empty_response")
        return CompletionResult(raw)
