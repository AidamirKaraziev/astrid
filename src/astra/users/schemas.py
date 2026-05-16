from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    telegram_id: int
    username: str | None
    onboarding_completed: bool
    points: int
    streak_current: int
    streak_best: int


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    display_name: str
    birth_date: date
    birth_time: time | None
    birth_place: str | None
    city: str
    timezone: str
    accuracy_percent: int
    accuracy_hint: str


class UserMeRead(BaseModel):
    user: UserRead
    profile: ProfileRead | None


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    birth_time: time | None = None
    birth_place: str | None = Field(None, max_length=255)
