"""Генерация ежедневного прогноза Astrid v4 через DeepSeek.

Фичи (predictions, tarot, zodiac) знают только get_daily_provider() /
daily_provider_enabled() — конкретный провайдер выбирается здесь.
"""

from __future__ import annotations

from astra.astro.daily_context import DailyContextV2
from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger
from astra.llm.base import BaseLlmProvider
from astra.llm.factory import get_deepseek_provider
from astra.llm.prompts.astrid import (
    sanitize_prediction_output,
    validate_prediction_output,
)
from astra.llm.prompts.astrid_v4 import SYSTEM_PROMPT_V4, build_user_message_v4
from astra.llm.types import ChatMessage, CompletionRequest

log = get_logger(__name__)

_DAILY_TEMPERATURE = 0.75
_DAILY_MAX_TOKENS = 600


def get_daily_provider(settings: Settings | None = None) -> BaseLlmProvider:
    return get_deepseek_provider(settings or get_settings())


def daily_provider_enabled(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
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
    if validation_error is None:
        validation_error = _validate_conflict_line(cleaned)
    if validation_error:
        log.warning(
            Event.LLM_VALIDATION_FAILED,
            provider=llm.name,
            reason=validation_error,
            prompt_version="v4",
        )
        return None, validation_error

    return cleaned, ""


def _validate_conflict_line(cleaned: str) -> str | None:
    """Третий блок — развилка «A — или B»: обязательное «или», не вопрос."""
    blocks = [b.strip() for b in cleaned.split("\n\n") if b.strip()]
    if len(blocks) < 3:
        return "invalid_structure"
    conflict_line = blocks[-1]
    if "или" not in conflict_line.lower():
        return "conflict_line_no_or"
    if conflict_line.endswith("?"):
        return "conflict_line_is_question"
    return None
