"""Генерация JSON совместимости через любой LLM-провайдер."""

from __future__ import annotations

import logging

from astra.core.config import Settings, get_settings
from astra.llm.base import BaseLlmProvider
from astra.llm.prompts.compatibility import (
    build_compatibility_system_prompt,
    build_compatibility_user_message,
    parse_compatibility_response,
)
from astra.llm.schemas.compatibility import CompatibilityLlmOutput, CompatibilityPromptInput
from astra.llm.types import ChatMessage, CompletionRequest

logger = logging.getLogger(__name__)

_COMPATIBILITY_TEMPERATURE = 0.7
_COMPATIBILITY_MAX_TOKENS = 8192


def build_compatibility_completion_request(
    prompt_input: CompatibilityPromptInput,
    provider: BaseLlmProvider,
    settings: Settings | None = None,
) -> CompletionRequest:
    """Собрать CompletionRequest для промпта синастрии."""
    cfg = settings or get_settings()
    messages = (
        ChatMessage("system", build_compatibility_system_prompt()),
        ChatMessage("user", build_compatibility_user_message(prompt_input)),
    )

    timeout_by_provider = {
        "openai": cfg.openai_timeout_seconds,
        "deepseek": cfg.deepseek_timeout_seconds,
        "grok": cfg.grok_timeout_seconds,
        "gemini": cfg.gemini_timeout_seconds,
        "openrouter": cfg.openrouter_timeout_seconds,
        "ollama": cfg.ollama_timeout_seconds,
    }
    timeout_seconds = timeout_by_provider.get(
        provider.name,
        cfg.openai_timeout_seconds,
    )

    extra: dict[str, object] = {}
    if provider.name in {"openai", "deepseek"}:
        extra["json_mode"] = True
    if provider.name == "deepseek":
        # V4 включает thinking по умолчанию — отключаем для JSON и цены
        extra["thinking_disabled"] = True
    if provider.name == "ollama":
        extra["num_ctx"] = 16384
        extra["think"] = False

    temperature = None if provider.name == "openai" else _COMPATIBILITY_TEMPERATURE

    return CompletionRequest(
        messages=messages,
        temperature=temperature,
        max_tokens=_COMPATIBILITY_MAX_TOKENS,
        timeout_seconds=timeout_seconds,
        extra=extra,
    )


async def generate_compatibility_output(
    prompt_input: CompatibilityPromptInput,
    provider: BaseLlmProvider,
    settings: Settings | None = None,
) -> tuple[CompatibilityLlmOutput | None, str]:
    """Сгенерировать структурированный разбор совместимости."""
    cfg = settings or get_settings()
    result = await provider.complete(
        build_compatibility_completion_request(prompt_input, provider, cfg),
    )
    if not result.text:
        return None, result.reason or "empty_response"

    parsed, error = parse_compatibility_response(result.text)
    if parsed is None:
        logger.warning(
            "Compatibility output failed validation via %s: %s",
            provider.name,
            error,
        )
        return None, error or "validation_error"

    return parsed, ""
