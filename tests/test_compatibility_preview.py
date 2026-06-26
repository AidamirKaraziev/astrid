from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from astra.llm.astrid_generate import build_astrid_completion_request, generate_astrid_body
from astra.llm.api.gemini import GeminiProvider
from astra.llm.api.grok import GrokProvider
from astra.llm.api.openrouter import OpenRouterProvider
from astra.llm.local.ollama import OllamaProvider
from astra.llm.types import CompletionResult
from astra.telegram.handlers.compatibility_preview import (
    OPENROUTER_NOT_CONFIGURED_TEXT,
    _failure_message,
    compatibility_openrouter_preview,
)


def test_build_astrid_completion_request_ollama_extra() -> None:
    provider = OllamaProvider(
        SimpleNamespace(
            ollama_timeout_seconds=120.0,
            grok_timeout_seconds=60.0,
            gemini_timeout_seconds=45.0,
            openrouter_timeout_seconds=75.0,
        ),
    )
    request = build_astrid_completion_request("hello", provider)
    assert request.extra["num_ctx"] == 4096
    assert request.extra["think"] is False
    assert request.max_tokens == 340


def test_build_astrid_completion_request_grok_no_ollama_extra() -> None:
    settings = SimpleNamespace(
        ollama_timeout_seconds=120.0,
        grok_timeout_seconds=90.0,
        gemini_timeout_seconds=45.0,
        openrouter_timeout_seconds=75.0,
    )
    provider = GrokProvider(settings)
    request = build_astrid_completion_request("hello", provider, settings)
    assert request.extra == {}
    assert request.timeout_seconds == 90.0


def test_build_astrid_completion_request_openrouter_timeout() -> None:
    settings = SimpleNamespace(
        ollama_timeout_seconds=120.0,
        grok_timeout_seconds=90.0,
        gemini_timeout_seconds=45.0,
        openrouter_timeout_seconds=75.0,
    )
    provider = OpenRouterProvider(settings)
    request = build_astrid_completion_request("hello", provider, settings)
    assert request.extra == {}
    assert request.timeout_seconds == 75.0


@pytest.mark.anyio
async def test_generate_astrid_body_success() -> None:
    provider = AsyncMock()
    provider.name = "openrouter"
    provider.complete = AsyncMock(return_value=CompletionResult("raw text"))

    ctx = SimpleNamespace()
    profile = SimpleNamespace(display_name="Аня")
    chart = SimpleNamespace()

    with patch(
        "astra.llm.astrid_generate.build_user_message",
        return_value="user prompt",
    ):
        with patch(
            "astra.llm.astrid_generate.sanitize_prediction_output",
            return_value="clean text",
        ):
            with patch(
                "astra.llm.astrid_generate.validate_prediction_output",
                return_value=None,
            ):
                text, reason = await generate_astrid_body(
                    ctx,
                    profile,
                    chart,
                    provider,
                )

    assert text == "clean text"
    assert reason == ""


def test_failure_message_maps_known_reasons() -> None:
    assert _failure_message("timeout").startswith("OpenRouter не ответил")
    assert _failure_message("http_401").startswith("OpenRouter API")
    assert _failure_message("http_429:Provider returned error").startswith("Free-модель")
    assert _failure_message("disabled") == OPENROUTER_NOT_CONFIGURED_TEXT


@pytest.mark.anyio
async def test_compatibility_openrouter_preview_not_configured() -> None:
    message = AsyncMock()
    message.from_user.id = 42
    message.answer = AsyncMock()
    session = AsyncMock()

    user = SimpleNamespace(
        onboarding_completed=True,
        profile=SimpleNamespace(timezone="Europe/Moscow"),
    )

    with patch(
        "astra.telegram.handlers.compatibility_preview.users_crud.get_user_by_telegram_id",
        new_callable=AsyncMock,
        return_value=user,
    ):
        with patch(
            "astra.telegram.handlers.compatibility_preview.get_openrouter_provider",
        ) as get_provider:
            get_provider.return_value.is_configured.return_value = False
            await compatibility_openrouter_preview(message, session)

    message.answer.assert_awaited_once()
    assert "OPENROUTER_ENABLED" in message.answer.await_args.args[0]
