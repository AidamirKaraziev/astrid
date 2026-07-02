from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class TaskType(StrEnum):
    NATAL_CHART_GENERATE = "natal_chart.generate"
    PREDICTION_GENERATE = "prediction.generate"
    PREDICTION_SEND = "prediction.send"
    COMPATIBILITY_GENERATE = "compatibility.generate"


class TaskMessage(BaseModel):
    type: TaskType
    user_id: UUID | None = None
    report_id: UUID | None = None
    prediction_date: date | None = None
    retry: int = Field(default=0, ge=0)
