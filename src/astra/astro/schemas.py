from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class NatalChartData(BaseModel):
    accuracy_tier: int
    sun_sign: str
    moon_sign: str | None = None
    asc_sign: str | None = None
    planets: dict[str, float] = Field(default_factory=dict)
    birth_lat: float | None = None
    birth_lon: float | None = None
    timezone: str = "Europe/Moscow"
    profile_snapshot: dict[str, str | None] = Field(default_factory=dict)


class TransitAspect(BaseModel):
    transit_planet: str
    aspect: str
    natal_planet: str
    orb_deg: float
    theme: str = ""


class AstroContext(BaseModel):
    date: date
    accuracy_tier: int
    natal: dict[str, str | None]
    transits: list[TransitAspect]
    moon_phase: str | None = None

    def model_dump_json_safe(self) -> dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "accuracy_tier": self.accuracy_tier,
            "natal": self.natal,
            "transits": [t.model_dump() for t in self.transits],
            "moon_phase": self.moon_phase,
        }
