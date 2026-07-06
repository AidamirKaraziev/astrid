"""Генерация JSON разбора натала через DeepSeek (3 шага + assemble)."""

from __future__ import annotations

from collections.abc import Callable

from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger
from astra.llm.base import BaseLlmProvider
from astra.llm.compatibility_generate import _build_step_request
from astra.llm.prompts.natal import (
    CONTENT_SYSTEM_PROMPT,
    POLISH_SYSTEM_PROMPT,
    SKELETON_SYSTEM_PROMPT,
    assemble_from_pipeline as _assemble_from_pipeline,
    build_content_user_message,
    build_polish_user_message,
    build_skeleton_user_message,
    parse_natal_content,
    parse_natal_polish,
    parse_natal_skeleton,
)
from astra.llm.schemas.natal import NatalLlmOutput, NatalPromptInput

log = get_logger(__name__)

_JSON_RETRY_ATTEMPTS = 3


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
            log.warning(
                Event.NATAL_REPORT_LLM_STEP_FAILED,
                step=step_name,
                provider=provider.name,
                attempt=attempt,
                reason=last_error,
            )
            continue

        parsed, error = parse_fn(result.text)
        if parsed is not None:
            return parsed, ""

        last_error = error or "validation_error"
        log.warning(
            Event.NATAL_REPORT_LLM_STEP_FAILED,
            step=step_name,
            provider=provider.name,
            attempt=attempt,
            reason=last_error,
        )
        if not (last_error or "").startswith("json_invalid"):
            return None, last_error

    return None, last_error


async def generate_natal_output(
    prompt_input: NatalPromptInput,
    provider: BaseLlmProvider,
    settings: Settings | None = None,
) -> tuple[NatalLlmOutput | None, str]:
    """Три шага LLM → merge → assemble → NatalLlmOutput."""
    cfg = settings or get_settings()
    aspects_count = len(prompt_input.aspects)

    skeleton, err = await _complete_json_step(
        provider,
        cfg,
        step_name="skeleton",
        system_prompt=SKELETON_SYSTEM_PROMPT,
        user_message=build_skeleton_user_message(prompt_input),
        parse_fn=parse_natal_skeleton,
    )
    if skeleton is None:
        return None, err

    content, err = await _complete_json_step(
        provider,
        cfg,
        step_name="content",
        system_prompt=CONTENT_SYSTEM_PROMPT,
        user_message=build_content_user_message(prompt_input, skeleton),
        parse_fn=parse_natal_content,
    )
    if content is None:
        return None, err
    if len(content.aspect_interpretations) != aspects_count:
        return None, (
            f"validation: aspect_interpretations {len(content.aspect_interpretations)} "
            f"!= {aspects_count}"
        )

    polish, err = await _complete_json_step(
        provider,
        cfg,
        step_name="polish",
        system_prompt=POLISH_SYSTEM_PROMPT,
        user_message=build_polish_user_message(prompt_input, content),
        parse_fn=parse_natal_polish,
    )
    if polish is None:
        return None, err
    if len(polish.aspect_interpretations) != aspects_count:
        return None, (
            f"validation: polish aspect_interpretations {len(polish.aspect_interpretations)} "
            f"!= {aspects_count}"
        )

    try:
        return _assemble_from_pipeline(prompt_input, content, polish), ""
    except Exception as exc:
        log.exception(Event.NATAL_REPORT_ASSEMBLE_FAILED, error_type=type(exc).__name__)
        return None, f"assemble: {exc}"
