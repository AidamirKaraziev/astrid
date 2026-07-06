from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class TaskType(StrEnum):
    NATAL_CHART_GENERATE = "natal_chart.generate"
    DAILY_CONTEXT_BUILD = "daily_context.build"
    PREDICTION_GENERATE = "prediction.generate"
    PREDICTION_SEND = "prediction.send"
    SYNASTRY_BUILD = "synastry.build"
    COMPATIBILITY_GENERATE = "compatibility.generate"
    PDF_GENERATE = "pdf.generate"
    COMPATIBILITY_SEND = "compatibility.send"
    NATAL_GENERATE = "natal_report.generate"
    NATAL_PDF_GENERATE = "natal_report.pdf"
    NATAL_SEND = "natal_report.send"


class TaskMessage(BaseModel):
    type: TaskType
    user_id: UUID | None = None
    report_id: UUID | None = None
    prediction_date: date | None = None
    correlation_id: str | None = None
    retry: int = Field(default=0, ge=0)
