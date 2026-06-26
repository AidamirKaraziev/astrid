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
class CompletionResult:
    text: str | None
    reason: str = ""
