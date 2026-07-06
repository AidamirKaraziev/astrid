from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class NatalChartData(BaseModel):
    accuracy_tier: int
    sun_sign: str
    moon_sign: str | None = None
    asc_sign: str | None = None
    planet_signs: dict[str, str] = Field(default_factory=dict)
    planets: dict[str, float] = Field(default_factory=dict)
    birth_lat: float | None = None
    birth_lon: float | None = None
    timezone: str = "Europe/Moscow"
    profile_snapshot: dict[str, str | None] = Field(default_factory=dict)


class ChartPoint(BaseModel):
    """Точка полной натальной карты (планета, узел, Хирон, Лилит)."""

    name: str  # en-ключ kerykeion: "Sun", "Chiron", "True_North_Lunar_Node"
    name_ru: str
    lon: float  # абсолютная эклиптическая долгота 0–360
    sign: str  # знак по-русски
    sign_deg: float  # градус внутри знака 0–30
    house: int | None = None  # None, если время рождения неизвестно
    retrograde: bool = False
    element: str | None = None  # огонь/земля/воздух/вода (у узлов/Лилит — None)
    modality: str | None = None  # кардинальный/фиксированный/мутабельный
    dignity: str | None = None  # обитель/экзальтация/изгнание/падение


class HouseCusp(BaseModel):
    number: int  # 1–12
    lon: float
    sign: str


class NatalAspect(BaseModel):
    p1: str  # en-ключ точки
    p1_ru: str
    p2: str
    p2_ru: str
    aspect: str  # по-русски: соединение/секстиль/квадрат/трин/оппозиция
    aspect_en: str
    orb_deg: float


class FullNatalChart(BaseModel):
    """Полная карта для разбора натала. Снапшотится в natal_reports.chart_data."""

    schema_version: int = 1
    has_time: bool
    moon_sign_uncertain: bool = False  # без времени Луна могла сменить знак за сутки
    points: list[ChartPoint]
    asc: ChartPoint | None = None
    mc: ChartPoint | None = None
    houses: list[HouseCusp] | None = None
    aspects: list[NatalAspect] = Field(default_factory=list)
    element_balance: dict[str, float] = Field(default_factory=dict)  # RU-стихия → вес
    modality_balance: dict[str, float] = Field(default_factory=dict)  # RU-крест → вес
    moon_phase: str | None = None
    birth_lat: float | None = None
    birth_lon: float | None = None
    timezone: str = "Europe/Moscow"

    def point(self, name: str) -> ChartPoint | None:
        return next((p for p in self.points if p.name == name), None)


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
