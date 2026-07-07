"""Генерация ежедневного прогноза Astrid v4: DeepSeek (или Ollama по настройке)."""

from __future__ import annotations

from astra.astro.daily_context import DailyContextV2
from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger
from astra.llm.base import BaseLlmProvider
from astra.llm.factory import get_deepseek_provider, get_ollama_provider
from astra.llm.prompts.astrid import (
    sanitize_prediction_output,
    validate_prediction_output,
)
from astra.llm.prompts.astrid_v4 import SYSTEM_PROMPT_V4, build_user_message_v4
from astra.llm.types import ChatMessage, CompletionRequest

log = get_logger(__name__)

_DAILY_TEMPERATURE = 0.75
_DAILY_MAX_TOKENS = 600
_OLLAMA_NUM_CTX = 4096


def get_daily_provider(settings: Settings | None = None) -> BaseLlmProvider:
    cfg = settings or get_settings()
    if cfg.daily_llm_provider == "ollama":
        return get_ollama_provider(cfg)
    return get_deepseek_provider(cfg)


def daily_provider_enabled(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    if cfg.daily_llm_provider == "ollama":
        return cfg.ollama_enabled
    return cfg.deepseek_enabled and bool(cfg.deepseek_api_key)


def _build_request(
    user_message: str,
    provider: BaseLlmProvider,
    cfg: Settings,
) -> CompletionRequest:
    messages = (
        ChatMessage("system", SYSTEM_PROMPT_V4),
        ChatMessage("user", user_message),
    )
    if provider.name == "ollama":
        return CompletionRequest(
            messages=messages,
            temperature=_DAILY_TEMPERATURE,
            max_tokens=_DAILY_MAX_TOKENS,
            timeout_seconds=cfg.ollama_timeout_seconds,
            extra={"num_ctx": _OLLAMA_NUM_CTX, "think": False, "keep_alive": "30m"},
        )
    extra: dict[str, object] = {}
    if provider.name == "deepseek":
        extra["thinking_disabled"] = True
    return CompletionRequest(
        messages=messages,
        temperature=_DAILY_TEMPERATURE,
        max_tokens=_DAILY_MAX_TOKENS,
        timeout_seconds=cfg.deepseek_timeout_seconds,
        extra=extra,
    )


async def generate_daily_body_v4(
    ctx: DailyContextV2,
    settings: Settings | None = None,
    *,
    provider: BaseLlmProvider | None = None,
) -> tuple[str | None, str]:
    """Сгенерировать 3 блока (вопрос/прогноз/шаг); (None, reason) при ошибке."""
    cfg = settings or get_settings()
    llm = provider or get_daily_provider(cfg)

    result = await llm.complete(_build_request(build_user_message_v4(ctx), llm, cfg))
    if not result.text:
        return None, result.reason or "empty_response"

    cleaned = sanitize_prediction_output(result.text)
    if not cleaned:
        return None, "sanitize_empty"

    validation_error = validate_prediction_output(cleaned, "", require_name=False)
    if validation_error:
        log.warning(
            Event.LLM_VALIDATION_FAILED,
            provider=llm.name,
            reason=validation_error,
            prompt_version="v4",
        )
        return None, validation_error

    return cleaned, ""
