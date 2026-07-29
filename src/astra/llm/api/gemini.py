"""Клиент Google Gemini API (AI Studio, нативный generateContent)."""

from __future__ import annotations

import httpx

from astra.core.config import Settings, get_settings
from astra.llm.base import BaseLlmProvider
from astra.llm.types import CompletionRequest, CompletionResult, usage_from_gemini


def _build_gemini_payload(request: CompletionRequest) -> dict[str, object]:
    system_chunks: list[str] = []
    contents: list[dict[str, object]] = []

    for message in request.messages:
        if message.role == "system":
            system_chunks.append(message.content)
            continue
        role = "model" if message.role == "assistant" else message.role
        contents.append({"role": role, "parts": [{"text": message.content}]})

    payload: dict[str, object] = {"contents": contents}
    if system_chunks:
        payload["systemInstruction"] = {
            "parts": [{"text": "\n\n".join(system_chunks)}],
        }

    generation_config: dict[str, object] = {}
    if request.temperature is not None:
        generation_config["temperature"] = request.temperature
    if request.max_tokens is not None:
        generation_config["maxOutputTokens"] = request.max_tokens
    if generation_config:
        payload["generationConfig"] = generation_config

    return payload


def _extract_gemini_text(data: dict[str, object]) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        return ""

    content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
    if not isinstance(content, dict):
        return ""

    parts = content.get("parts") or []
    texts: list[str] = []
    for part in parts:
        if isinstance(part, dict):
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
    return "\n".join(texts).strip()


class GeminiProvider(BaseLlmProvider):
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def settings(self) -> Settings:
        return self._settings

    def is_configured(self) -> bool:
        cfg = self._settings
        return cfg.gemini_enabled and bool(cfg.gemini_api_key.strip())

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        if not self.is_configured():
            return CompletionResult(None, "disabled")

        cfg = self._settings
        model = cfg.gemini_model.strip()
        url = f"{cfg.gemini_base_url.rstrip('/')}/models/{model}:generateContent"
        timeout = request.timeout_seconds or cfg.gemini_timeout_seconds
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": cfg.gemini_api_key.strip(),
        }
        payload = _build_gemini_payload(request)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            return CompletionResult(None, self.map_http_error(exc, log_label="Gemini"))

        if not isinstance(data, dict):
            return CompletionResult(None, "empty_response")

        raw = _extract_gemini_text(data)
        if not raw:
            block_reason = ""
            prompt_feedback = data.get("promptFeedback")
            if isinstance(prompt_feedback, dict):
                block_reason = str(prompt_feedback.get("blockReason") or "")
            if block_reason:
                return CompletionResult(None, f"blocked:{block_reason}")
            return CompletionResult(None, "empty_response")

        return CompletionResult(
            raw,
            model=data.get("modelVersion") or cfg.gemini_model,
            usage=usage_from_gemini(data),
        )
