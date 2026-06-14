"""Ошибки генерации предсказаний и отчёты в Sentry."""

from __future__ import annotations

from datetime import date
from uuid import UUID

import sentry_sdk

from astra.core.config import get_settings

_REASON_LABELS: dict[str, str] = {
    "disabled": "Ollama отключена",
    "timeout": "таймаут Ollama",
    "connection": "нет соединения с Ollama",
    "empty_response": "пустой ответ Ollama",
    "sanitize_empty": "ответ не прошёл постобработку",
    "request_error": "ошибка запроса к Ollama",
}


class LlmGenerationError(Exception):
    """LLM не вернула валидный прогноз."""

    def __init__(self, reason: str, *, detail: str | None = None) -> None:
        self.reason = reason
        self.detail = detail
        label = _REASON_LABELS.get(reason, reason)
        message = f"Предсказание: {label}"
        if detail:
            message = f"{message} ({detail})"
        super().__init__(message)


def _human_reason(reason: str) -> str:
    return _REASON_LABELS.get(reason, reason)


def report_prediction_generation_failure(
    *,
    user_id: UUID,
    prediction_date: date,
    reason: str,
    attempts: int,
    elapsed_sec: float,
    final: bool = False,
) -> None:
    """Человекочитаемое событие в Sentry для мониторинга сбоев генерации."""
    if not sentry_sdk.is_initialized():
        return

    cfg = get_settings()
    label = _human_reason(reason)
    if final:
        message = f"Предсказание: {label} после {attempts} попыток"
        level = "error"
    else:
        message = f"Предсказание: повтор после {label} (попытка {attempts})"
        level = "warning"

    with sentry_sdk.push_scope() as scope:
        scope.set_tag("prediction_failure", "true")
        scope.set_tag("prediction_failure_final", str(final).lower())
        scope.set_tag("failure_reason", reason)
        scope.set_tag("ollama_model", cfg.ollama_model)
        scope.set_tag("service", cfg.sentry_service)
        scope.set_context(
            "prediction_generation",
            {
                "user_id": str(user_id),
                "prediction_date": prediction_date.isoformat(),
                "attempts": attempts,
                "elapsed_sec": round(elapsed_sec, 1),
                "reason": reason,
                "reason_label": label,
            },
        )
        scope.fingerprint = ["prediction-llm", reason]
        sentry_sdk.capture_message(message, level=level)
