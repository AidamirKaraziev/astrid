"""Этапы прогресса генерации (daily + совместимость)."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from uuid import UUID


class PredictionStage(StrEnum):
    STARTED = "started"
    NATAL_DONE = "natal_done"
    CONTEXT_DONE = "context_done"


class CompatibilityStage(StrEnum):
    STARTED = "started"
    SYNASTRY_DONE = "synastry_done"
    LLM_DONE = "llm_done"


def prediction_job_key(target: date) -> str:
    return f"prediction:{target.isoformat()}"


def compatibility_job_key(report_id: UUID) -> str:
    return f"compatibility:{report_id}"
