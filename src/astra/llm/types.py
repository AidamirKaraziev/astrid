"""Общие типы для LLM-провайдеров."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    messages: tuple[ChatMessage, ...]
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: float | None = None
    extra: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Расход токенов за вызов. None у поля — провайдер его не вернул."""

    prompt: int | None = None
    completion: int | None = None

    @property
    def known(self) -> bool:
        return self.prompt is not None or self.completion is not None


@dataclass(frozen=True, slots=True)
class CompletionResult:
    text: str | None
    reason: str = ""
    # Модель и расход — для учёта себестоимости. Пустые, если провайдер молчит:
    # лучше дырка в отчёте, чем выдуманное число.
    model: str | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)


def usage_from_openai(data: dict) -> TokenUsage:
    """Разбор блока usage у OpenAI-совместимых API (DeepSeek, Grok, OpenRouter)."""
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return TokenUsage()
    return TokenUsage(
        prompt=usage.get("prompt_tokens"),
        completion=usage.get("completion_tokens"),
    )


def usage_from_gemini(data: dict) -> TokenUsage:
    """У Gemini блок называется иначе и лежит отдельно от кандидатов."""
    usage = data.get("usageMetadata")
    if not isinstance(usage, dict):
        return TokenUsage()
    return TokenUsage(
        prompt=usage.get("promptTokenCount"),
        completion=usage.get("candidatesTokenCount"),
    )
