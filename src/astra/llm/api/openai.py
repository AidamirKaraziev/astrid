"""Клиент OpenAI API (chat completions)."""

from __future__ import annotations

import httpx

from astra.core.config import Settings, get_settings
from astra.llm.base import BaseLlmProvider
from astra.llm.types import CompletionRequest, CompletionResult, usage_from_openai


def _is_gpt5_model(model: str) -> bool:
    slug = model.strip().lower()
    return slug.startswith("gpt-5") or slug.startswith("o1") or slug.startswith("o3")


class OpenAIProvider(BaseLlmProvider):
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def name(self) -> str:
        return "openai"

    @property
    def settings(self) -> Settings:
        return self._settings

    def is_configured(self) -> bool:
        cfg = self._settings
        return cfg.openai_enabled and bool(cfg.openai_api_key.strip())

    def _build_payload(self, request: CompletionRequest, cfg: Settings) -> dict[str, object]:
        model = cfg.openai_model
        payload: dict[str, object] = {
            "model": model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "stream": False,
        }

        if request.extra.get("json_mode"):
            payload["response_format"] = {"type": "json_object"}

        if request.temperature is not None and not _is_gpt5_model(model):
            payload["temperature"] = request.temperature

        if request.max_tokens is not None:
            token_key = (
                "max_completion_tokens"
                if _is_gpt5_model(model)
                else "max_tokens"
            )
            payload[token_key] = request.max_tokens

        return payload

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        if not self.is_configured():
            return CompletionResult(None, "disabled")

        cfg = self._settings
        payload = self._build_payload(request, cfg)
        url = f"{cfg.openai_base_url.rstrip('/')}/chat/completions"
        timeout = request.timeout_seconds or cfg.openai_timeout_seconds
        headers = {
            "Authorization": f"Bearer {cfg.openai_api_key.strip()}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            return CompletionResult(None, self.map_http_error(exc, log_label="OpenAI"))

        choices = data.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            return CompletionResult(None, "empty_response")

        message = choices[0].get("message") or {}
        if not isinstance(message, dict):
            return CompletionResult(None, "empty_response")

        raw = (message.get("content") or "").strip()
        if not raw:
            return CompletionResult(None, "empty_response")
        return CompletionResult(
            raw,
            model=data.get("model"),
            usage=usage_from_openai(data),
        )
