"""Фабрика LLM-провайдеров."""

from __future__ import annotations

from astra.core.config import Settings, get_settings
from astra.llm.api.deepseek import DeepSeekProvider
from astra.llm.api.gemini import GeminiProvider
from astra.llm.api.grok import GrokProvider
from astra.llm.api.openai import OpenAIProvider
from astra.llm.api.openrouter import OpenRouterProvider
from astra.llm.base import BaseLlmProvider
from astra.llm.local.ollama import OllamaProvider
from astra.llm.tracing_provider import TracingLlmProvider

_KNOWN_PROVIDERS = frozenset({"ollama", "grok", "gemini", "openrouter", "openai", "deepseek"})


def _wrap(provider: BaseLlmProvider, *, purpose: str = "unknown") -> BaseLlmProvider:
    return TracingLlmProvider(provider, purpose=purpose)


def get_llm_provider(name: str, settings: Settings | None = None, *, purpose: str = "unknown") -> BaseLlmProvider:
    """Вернуть провайдер по имени (с tracing-обёрткой)."""
    provider = name.strip().lower()
    if provider not in _KNOWN_PROVIDERS:
        raise ValueError(f"Unknown LLM provider: {name}")

    cfg = settings or get_settings()
    if provider == "ollama":
        return _wrap(OllamaProvider(cfg), purpose=purpose)
    if provider == "grok":
        return _wrap(GrokProvider(cfg), purpose=purpose)
    if provider == "gemini":
        return _wrap(GeminiProvider(cfg), purpose=purpose)
    if provider == "openai":
        return _wrap(OpenAIProvider(cfg), purpose=purpose)
    if provider == "deepseek":
        return _wrap(DeepSeekProvider(cfg), purpose=purpose)
    return _wrap(OpenRouterProvider(cfg), purpose=purpose)


def get_ollama_provider(settings: Settings | None = None) -> BaseLlmProvider:
    return _wrap(OllamaProvider(settings or get_settings()), purpose="daily_prediction")


def get_grok_provider(settings: Settings | None = None) -> BaseLlmProvider:
    return _wrap(GrokProvider(settings or get_settings()), purpose="grok")


def get_gemini_provider(settings: Settings | None = None) -> BaseLlmProvider:
    return _wrap(GeminiProvider(settings or get_settings()), purpose="gemini")


def get_openrouter_provider(settings: Settings | None = None) -> BaseLlmProvider:
    return _wrap(OpenRouterProvider(settings or get_settings()), purpose="openrouter")


def get_openai_provider(settings: Settings | None = None) -> BaseLlmProvider:
    return _wrap(OpenAIProvider(settings or get_settings()), purpose="openai")


def get_deepseek_provider(settings: Settings | None = None) -> BaseLlmProvider:
    return _wrap(DeepSeekProvider(settings or get_settings()), purpose="compatibility")
