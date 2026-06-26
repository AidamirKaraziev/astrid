"""Генерация Astrid v3 через любой LLM-провайдер."""

from __future__ import annotations

import logging

from astra.astro.schemas import AstroContext, NatalChartData
from astra.core.config import Settings, get_settings
from astra.llm.base import BaseLlmProvider
from astra.llm.types import ChatMessage, CompletionRequest
from astra.llm.prompts.astrid import (
    QuestionArchetype,
    build_system_prompt,
    build_user_message,
    sanitize_prediction_output,
    validate_prediction_output,
)
from astra.users.models import Profile

logger = logging.getLogger(__name__)

_ASTRID_TEMPERATURE = 0.76
_ASTRID_NUM_PREDICT = 340
_ASTRID_NUM_CTX = 4096


def build_astrid_completion_request(
    user_message: str,
    provider: BaseLlmProvider,
    settings: Settings | None = None,
) -> CompletionRequest:
    """Собрать CompletionRequest для Astrid v3 под конкретный провайдер."""
    cfg = settings or get_settings()
    messages = (
        ChatMessage("system", build_system_prompt()),
        ChatMessage("user", user_message),
    )
    if provider.name == "ollama":
        return CompletionRequest(
            messages=messages,
            temperature=_ASTRID_TEMPERATURE,
            max_tokens=_ASTRID_NUM_PREDICT,
            timeout_seconds=cfg.ollama_timeout_seconds,
            extra={"num_ctx": _ASTRID_NUM_CTX, "think": False, "keep_alive": "30m"},
        )

    timeout_by_provider = {
        "grok": cfg.grok_timeout_seconds,
        "gemini": cfg.gemini_timeout_seconds,
        "openrouter": cfg.openrouter_timeout_seconds,
    }
    timeout_seconds = timeout_by_provider.get(provider.name, cfg.openrouter_timeout_seconds)

    return CompletionRequest(
        messages=messages,
        temperature=_ASTRID_TEMPERATURE,
        max_tokens=_ASTRID_NUM_PREDICT,
        timeout_seconds=timeout_seconds,
    )


async def generate_astrid_body(
    ctx: AstroContext,
    profile: Profile,
    chart: NatalChartData,
    provider: BaseLlmProvider,
    settings: Settings | None = None,
    *,
    archetype: QuestionArchetype | None = None,
) -> tuple[str | None, str]:
    """Сгенерировать текст Astrid v3; (None, reason) — ошибка или пустой ответ."""
    cfg = settings or get_settings()
    display_name = (profile.display_name or "").strip() or "друг"
    user_message = build_user_message(ctx, profile, chart, archetype=archetype)
    result = await provider.complete(
        build_astrid_completion_request(user_message, provider, cfg),
    )
    if not result.text:
        return None, result.reason or "empty_response"

    cleaned = sanitize_prediction_output(result.text)
    if not cleaned:
        return None, "sanitize_empty"

    validation_error = validate_prediction_output(cleaned, display_name)
    if validation_error:
        logger.warning(
            "Astrid output failed validation via %s: %s (archetype=%s)",
            provider.name,
            validation_error,
            archetype.id if archetype is not None else "auto",
        )
        return None, validation_error

    return cleaned, ""
