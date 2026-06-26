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

_KNOWN_PROVIDERS = frozenset({"ollama", "grok", "gemini", "openrouter", "openai", "deepseek"})


def get_llm_provider(name: str, settings: Settings | None = None) -> BaseLlmProvider:
    """Вернуть провайдер по имени."""
    provider = name.strip().lower()
    if provider not in _KNOWN_PROVIDERS:
        raise ValueError(f"Unknown LLM provider: {name}")

    cfg = settings or get_settings()
    if provider == "ollama":
        return OllamaProvider(cfg)
    if provider == "grok":
        return GrokProvider(cfg)
    if provider == "gemini":
        return GeminiProvider(cfg)
    if provider == "openai":
        return OpenAIProvider(cfg)
    if provider == "deepseek":
        return DeepSeekProvider(cfg)
    return OpenRouterProvider(cfg)


def get_ollama_provider(settings: Settings | None = None) -> OllamaProvider:
    return OllamaProvider(settings or get_settings())


def get_grok_provider(settings: Settings | None = None) -> GrokProvider:
    return GrokProvider(settings or get_settings())


def get_gemini_provider(settings: Settings | None = None) -> GeminiProvider:
    return GeminiProvider(settings or get_settings())


def get_openrouter_provider(settings: Settings | None = None) -> OpenRouterProvider:
    return OpenRouterProvider(settings or get_settings())


def get_openai_provider(settings: Settings | None = None) -> OpenAIProvider:
    return OpenAIProvider(settings or get_settings())


def get_deepseek_provider(settings: Settings | None = None) -> DeepSeekProvider:
    return DeepSeekProvider(settings or get_settings())
