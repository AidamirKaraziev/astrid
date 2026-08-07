from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from astra.users.gender import Gender, normalize_gender


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
    gender: Gender | None = None
    # Пусто у прошедших короткий онбординг: астроданные добираются позже.
    birth_date: date | None = None
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
    gender: Gender | None = None
    birth_date: date | None = None
    birth_time: time | None = None
    birth_place: str | None = Field(None, max_length=255)

    @field_validator("gender", mode="before")
    @classmethod
    def _validate_gender(cls, value: object) -> Gender | None:
        if value is None:
            return None
        normalized = normalize_gender(str(value))
        if normalized is None:
            msg = "gender must be 'мужчина' or 'женщина'"
            raise ValueError(msg)
        return normalized
