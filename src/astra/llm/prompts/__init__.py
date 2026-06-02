"""Промпты для генерации текста."""

from astra.llm.prompts.astrid import (
    MAX_SENTENCES,
    MIN_SENTENCES,
    build_system_prompt,
    build_user_message,
    sanitize_prediction_output,
)

__all__ = [
    "MAX_SENTENCES",
    "MIN_SENTENCES",
    "build_system_prompt",
    "build_user_message",
    "sanitize_prediction_output",
]
