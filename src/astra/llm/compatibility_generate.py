"""Генерация JSON совместимости через DeepSeek (3 шага + assemble)."""

from __future__ import annotations

import logging
from collections.abc import Callable

from astra.core.config import Settings, get_settings
from astra.llm.base import BaseLlmProvider
from astra.llm.prompts.compatibility import (
    CONTENT_SYSTEM_PROMPT,
    POLISH_SYSTEM_PROMPT,
    SKELETON_SYSTEM_PROMPT,
    assemble_from_pipeline as _assemble_from_pipeline,
    build_content_user_message,
    build_polish_user_message,
    build_skeleton_user_message,
    parse_content_raw,
    parse_narrative_skeleton,
    parse_polish_raw,
)
from astra.llm.schemas.compatibility import CompatibilityLlmOutput, CompatibilityPromptInput
from astra.llm.types import ChatMessage, CompletionRequest

logger = logging.getLogger(__name__)

_COMPATIBILITY_TEMPERATURE = 0.8
_COMPATIBILITY_MAX_TOKENS = 8192
_JSON_RETRY_ATTEMPTS = 3


def build_compatibility_completion_request(
    prompt_input: CompatibilityPromptInput,
    provider: BaseLlmProvider,
    settings: Settings | None = None,
) -> CompletionRequest:
    """CompletionRequest для шага 2 (контент) — для превью и тестов."""
    return _build_step_request(
        CONTENT_SYSTEM_PROMPT,
        build_content_user_message(
            prompt_input,
            _placeholder_skeleton(),
        ),
        provider,
        settings,
    )


def _placeholder_skeleton():
    from astra.llm.schemas.compatibility_raw import CompatibilityNarrativeSkeleton

    return CompatibilityNarrativeSkeleton(
        pair_story="(скелет)",
        central_tension="(напряжение)",
        growth_path="(рост)",
        metrics=[0.8, 0.7, 0.75, 0.7],
    )


def _build_step_request(
    system_prompt: str,
    user_message: str,
    provider: BaseLlmProvider,
    settings: Settings | None,
) -> CompletionRequest:
    cfg = settings or get_settings()
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
        extra["thinking_disabled"] = True
    if provider.name == "ollama":
        extra["num_ctx"] = 16384
        extra["think"] = False

    temperature = None if provider.name == "openai" else _COMPATIBILITY_TEMPERATURE

    return CompletionRequest(
        messages=(
            ChatMessage("system", system_prompt),
            ChatMessage("user", user_message),
        ),
        temperature=temperature,
        max_tokens=_COMPATIBILITY_MAX_TOKENS,
        timeout_seconds=timeout_seconds,
        extra=extra,
    )


async def _complete_json_step(
    provider: BaseLlmProvider,
    settings: Settings,
    *,
    step_name: str,
    system_prompt: str,
    user_message: str,
    parse_fn: Callable[[str], tuple[object | None, str | None]],
) -> tuple[object | None, str]:
    last_error = "unknown"
    for attempt in range(1, _JSON_RETRY_ATTEMPTS + 1):
        result = await provider.complete(
            _build_step_request(system_prompt, user_message, provider, settings),
        )
        if not result.text:
            last_error = result.reason or "empty_response"
            logger.warning(
                "Compatibility %s empty response via %s attempt %s: %s",
                step_name,
                provider.name,
                attempt,
                last_error,
            )
            continue

        parsed, error = parse_fn(result.text)
        if parsed is not None:
            return parsed, ""

        last_error = error or "validation_error"
        logger.warning(
            "Compatibility %s failed via %s attempt %s: %s; raw=%s",
            step_name,
            provider.name,
            attempt,
            last_error,
            result.text[:1500],
        )
        if not (last_error or "").startswith("json_invalid"):
            return None, last_error

    return None, last_error


async def generate_compatibility_output(
    prompt_input: CompatibilityPromptInput,
    provider: BaseLlmProvider,
    settings: Settings | None = None,
) -> tuple[CompatibilityLlmOutput | None, str]:
    """Три шага LLM → merge → assemble → CompatibilityLlmOutput."""
    cfg = settings or get_settings()

    skeleton, err = await _complete_json_step(
        provider,
        cfg,
        step_name="skeleton",
        system_prompt=SKELETON_SYSTEM_PROMPT,
        user_message=build_skeleton_user_message(prompt_input),
        parse_fn=parse_narrative_skeleton,
    )
    if skeleton is None:
        return None, err

    content, err = await _complete_json_step(
        provider,
        cfg,
        step_name="content",
        system_prompt=CONTENT_SYSTEM_PROMPT,
        user_message=build_content_user_message(prompt_input, skeleton),
        parse_fn=parse_content_raw,
    )
    if content is None:
        return None, err
    if len(content.aspect_interpretations) != len(prompt_input.aspects):
        return None, (
            f"validation: aspect_interpretations {len(content.aspect_interpretations)} "
            f"!= {len(prompt_input.aspects)}"
        )

    polish, err = await _complete_json_step(
        provider,
        cfg,
        step_name="polish",
        system_prompt=POLISH_SYSTEM_PROMPT,
        user_message=build_polish_user_message(prompt_input, content),
        parse_fn=parse_polish_raw,
    )
    if polish is None:
        return None, err
    if len(polish.aspect_interpretations) != len(prompt_input.aspects):
        return None, (
            f"validation: polish aspect_interpretations {len(polish.aspect_interpretations)} "
            f"!= {len(prompt_input.aspects)}"
        )

    try:
        return _assemble_from_pipeline(prompt_input, content, polish), ""
    except Exception as exc:
        logger.exception("Compatibility assemble failed")
        return None, f"assemble: {exc}"
