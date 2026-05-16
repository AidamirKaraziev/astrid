from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PredictionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    prediction_date: date
    text: str
    accuracy_percent: int
    sent_at: datetime | None
