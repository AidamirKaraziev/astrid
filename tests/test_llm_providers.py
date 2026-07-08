from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from astra.llm.api.deepseek import DeepSeekProvider
from astra.llm.api.gemini import GeminiProvider
from astra.llm.api.grok import GrokProvider
from astra.llm.api.openai import OpenAIProvider
from astra.llm.api.openrouter import OpenRouterProvider
from astra.llm.factory import (
    get_deepseek_provider,
    get_gemini_provider,
    get_grok_provider,
    get_llm_provider,
    get_openai_provider,
    get_openrouter_provider,
)
from astra.llm.tracing_provider import TracingLlmProvider
from astra.llm.types import ChatMessage, CompletionRequest


def _deepseek_settings(**overrides: object) -> SimpleNamespace:
    defaults = {
        "deepseek_enabled": True,
        "deepseek_api_key": "test-deepseek-key",
        "deepseek_model": "deepseek-v4-flash",
        "deepseek_base_url": "https://api.deepseek.com/v1",
        "deepseek_timeout_seconds": 120.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _openai_settings(**overrides: object) -> SimpleNamespace:
    defaults = {
        "openai_enabled": True,
        "openai_api_key": "test-openai-key",
        "openai_model": "gpt-5.5",
        "openai_base_url": "https://api.openai.com/v1",
        "openai_timeout_seconds": 60.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _openrouter_settings(**overrides: object) -> SimpleNamespace:
    defaults = {
        "openrouter_enabled": True,
        "openrouter_api_key": "test-openrouter-key",
        "openrouter_model": "qwen/qwen3-next-80b-a3b-instruct:free",
        "openrouter_fallback_models": (
            "google/gemma-4-31b-it:free,google/gemma-4-26b-a4b-it:free,"
            "mistralai/mistral-small-3.1-24b-instruct:free"
        ),
        "openrouter_base_url": "https://openrouter.ai/api/v1",
        "openrouter_timeout_seconds": 30.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _gemini_settings(**overrides: object) -> SimpleNamespace:
    defaults = {
        "gemini_enabled": True,
        "gemini_api_key": "test-gemini-key",
        "gemini_model": "gemini-2.0-flash",
        "gemini_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "gemini_timeout_seconds": 30.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _grok_settings(**overrides: object) -> SimpleNamespace:
    defaults = {
        "grok_enabled": True,
        "xai_api_key": "test-key",
        "grok_model": "grok-4-1-fast-non-reasoning",
        "grok_base_url": "https://api.x.ai/v1",
        "grok_timeout_seconds": 30.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_get_llm_provider_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm_provider("claude")


def test_get_llm_provider_ollama_raises() -> None:
    """Локальная LLM удалена: имя ollama больше не поддерживается."""
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm_provider("ollama")


def test_get_llm_provider_returns_typed_instances() -> None:
    assert isinstance(get_grok_provider(), TracingLlmProvider)
    assert isinstance(get_gemini_provider(), TracingLlmProvider)
    assert isinstance(get_openrouter_provider(), TracingLlmProvider)
    assert isinstance(get_openai_provider(), TracingLlmProvider)
    assert isinstance(get_deepseek_provider(), TracingLlmProvider)
    assert isinstance(get_llm_provider("grok"), TracingLlmProvider)
    assert isinstance(get_llm_provider("gemini"), TracingLlmProvider)
    assert isinstance(get_llm_provider("openrouter"), TracingLlmProvider)
    assert isinstance(get_llm_provider("openai"), TracingLlmProvider)
    assert isinstance(get_llm_provider("deepseek"), TracingLlmProvider)
    assert isinstance(get_deepseek_provider()._inner, DeepSeekProvider)


def test_grok_provider_is_configured() -> None:
    enabled = GrokProvider(_grok_settings())
    disabled = GrokProvider(_grok_settings(grok_enabled=False))
    no_key = GrokProvider(_grok_settings(xai_api_key=""))

    assert enabled.is_configured()
    assert not disabled.is_configured()
    assert not no_key.is_configured()


def test_gemini_provider_is_configured() -> None:
    enabled = GeminiProvider(_gemini_settings())
    disabled = GeminiProvider(_gemini_settings(gemini_enabled=False))
    no_key = GeminiProvider(_gemini_settings(gemini_api_key=""))

    assert enabled.is_configured()
    assert not disabled.is_configured()
    assert not no_key.is_configured()


def test_openrouter_provider_is_configured() -> None:
    enabled = OpenRouterProvider(_openrouter_settings())
    disabled = OpenRouterProvider(_openrouter_settings(openrouter_enabled=False))
    no_key = OpenRouterProvider(_openrouter_settings(openrouter_api_key=""))

    assert enabled.is_configured()
    assert not disabled.is_configured()
    assert not no_key.is_configured()


def test_openai_provider_is_configured() -> None:
    enabled = OpenAIProvider(_openai_settings())
    disabled = OpenAIProvider(_openai_settings(openai_enabled=False))
    no_key = OpenAIProvider(_openai_settings(openai_api_key=""))

    assert enabled.is_configured()
    assert not disabled.is_configured()
    assert not no_key.is_configured()


def test_deepseek_provider_is_configured() -> None:
    enabled = DeepSeekProvider(_deepseek_settings())
    disabled = DeepSeekProvider(_deepseek_settings(deepseek_enabled=False))
    no_key = DeepSeekProvider(_deepseek_settings(deepseek_api_key=""))

    assert enabled.is_configured()
    assert not disabled.is_configured()
    assert not no_key.is_configured()


@pytest.mark.anyio
async def test_deepseek_provider_complete_success() -> None:
    provider = DeepSeekProvider(_deepseek_settings())
    request = CompletionRequest(
        messages=(
            ChatMessage("system", "sys"),
            ChatMessage("user", "ping"),
        ),
        temperature=0.7,
        max_tokens=8192,
        extra={"json_mode": True, "thinking_disabled": True},
    )
    mock_response = httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": " pong "}}]},
        request=httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions"),
    )

    with patch(
        "astra.llm.api.deepseek.httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as post:
        result = await provider.complete(request)

    assert result.text == "pong"
    assert result.reason == ""
    post.assert_awaited_once()
    call_kwargs = post.await_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-deepseek-key"
    assert call_kwargs["json"]["model"] == "deepseek-v4-flash"
    assert call_kwargs["json"]["response_format"] == {"type": "json_object"}
    assert call_kwargs["json"]["thinking"] == {"type": "disabled"}
    assert call_kwargs["json"]["max_tokens"] == 8192


@pytest.mark.anyio
async def test_deepseek_provider_complete_disabled() -> None:
    provider = DeepSeekProvider(_deepseek_settings(deepseek_enabled=False))
    result = await provider.complete(
        CompletionRequest(messages=(ChatMessage("user", "ping"),)),
    )
    assert result.text is None
    assert result.reason == "disabled"


@pytest.mark.anyio
async def test_openai_provider_complete_success() -> None:
    provider = OpenAIProvider(_openai_settings())
    request = CompletionRequest(
        messages=(
            ChatMessage("system", "sys"),
            ChatMessage("user", "ping"),
        ),
        max_tokens=256,
        extra={"json_mode": True},
    )
    mock_response = httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": " pong "}}]},
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )

    with patch(
        "astra.llm.api.openai.httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as post:
        result = await provider.complete(request)

    assert result.text == "pong"
    assert result.reason == ""
    post.assert_awaited_once()
    call_kwargs = post.await_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-openai-key"
    assert call_kwargs["json"]["model"] == "gpt-5.5"
    assert call_kwargs["json"]["response_format"] == {"type": "json_object"}
    assert call_kwargs["json"]["max_completion_tokens"] == 256
    assert "temperature" not in call_kwargs["json"]


@pytest.mark.anyio
async def test_openai_provider_complete_disabled() -> None:
    provider = OpenAIProvider(_openai_settings(openai_enabled=False))
    result = await provider.complete(
        CompletionRequest(messages=(ChatMessage("user", "ping"),)),
    )
    assert result.text is None
    assert result.reason == "disabled"


@pytest.mark.anyio
async def test_openrouter_provider_complete_success() -> None:
    provider = OpenRouterProvider(_openrouter_settings())
    request = CompletionRequest(
        messages=(
            ChatMessage("system", "sys"),
            ChatMessage("user", "ping"),
        ),
        temperature=0.5,
        max_tokens=32,
    )
    mock_response = httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": " pong "}}]},
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )

    with patch(
        "astra.llm.api.openrouter.httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as post:
        result = await provider.complete(request)

    assert result.text == "pong"
    assert result.reason == ""
    post.assert_awaited_once()
    call_kwargs = post.await_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-openrouter-key"
    assert call_kwargs["json"]["model"] == "qwen/qwen3-next-80b-a3b-instruct:free"
    assert call_kwargs["json"]["models"] == [
        "google/gemma-4-31b-it:free",
        "google/gemma-4-26b-a4b-it:free",
        "mistralai/mistral-small-3.1-24b-instruct:free",
    ]


@pytest.mark.anyio
async def test_gemini_provider_complete_success() -> None:
    provider = GeminiProvider(_gemini_settings())
    request = CompletionRequest(
        messages=(
            ChatMessage("system", "sys"),
            ChatMessage("user", "ping"),
        ),
        temperature=0.5,
        max_tokens=32,
    )
    mock_response = httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [{"text": " pong "}],
                    },
                },
            ],
        },
        request=httpx.Request(
            "POST",
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        ),
    )

    with patch(
        "astra.llm.api.gemini.httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as post:
        result = await provider.complete(request)

    assert result.text == "pong"
    assert result.reason == ""
    post.assert_awaited_once()
    call_kwargs = post.await_args.kwargs
    assert call_kwargs["headers"]["x-goog-api-key"] == "test-gemini-key"
    assert call_kwargs["json"]["systemInstruction"]["parts"][0]["text"] == "sys"
    assert call_kwargs["json"]["contents"][0]["parts"][0]["text"] == "ping"


@pytest.mark.anyio
async def test_grok_provider_complete_success() -> None:
    provider = GrokProvider(_grok_settings())
    request = CompletionRequest(
        messages=(ChatMessage("user", "ping"),),
        temperature=0.5,
        max_tokens=32,
    )
    mock_response = httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": " pong "}}]},
        request=httpx.Request("POST", "https://api.x.ai/v1/chat/completions"),
    )

    with patch(
        "astra.llm.api.grok.httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as post:
        result = await provider.complete(request)

    assert result.text == "pong"
    assert result.reason == ""
    post.assert_awaited_once()
    call_kwargs = post.await_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert call_kwargs["json"]["model"] == "grok-4-1-fast-non-reasoning"


@pytest.mark.anyio
async def test_grok_provider_complete_disabled() -> None:
    provider = GrokProvider(_grok_settings(grok_enabled=False))
    result = await provider.complete(
        CompletionRequest(messages=(ChatMessage("user", "ping"),)),
    )
    assert result.text is None
    assert result.reason == "disabled"


@pytest.mark.anyio
async def test_grok_provider_complete_http_error() -> None:
    provider = GrokProvider(_grok_settings())
    mock_response = httpx.Response(
        401,
        request=httpx.Request("POST", "https://api.x.ai/v1/chat/completions"),
    )

    with patch(
        "astra.llm.api.grok.httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "unauthorized",
            request=mock_response.request,
            response=mock_response,
        ),
    ):
        result = await provider.complete(
            CompletionRequest(messages=(ChatMessage("user", "ping"),)),
        )

    assert result.text is None
    assert result.reason == "http_401"


@pytest.mark.anyio
async def test_grok_provider_complete_empty_content() -> None:
    provider = GrokProvider(_grok_settings())
    mock_response = httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": "   "}}]},
        request=httpx.Request("POST", "https://api.x.ai/v1/chat/completions"),
    )

    with patch(
        "astra.llm.api.grok.httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await provider.complete(
            CompletionRequest(messages=(ChatMessage("user", "ping"),)),
        )

    assert result.text is None
    assert result.reason == "empty_response"


