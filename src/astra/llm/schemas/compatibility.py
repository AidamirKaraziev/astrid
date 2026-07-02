"""Схемы ввода/вывода для промпта совместимости → PDF синастрии."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# --- совпадает с ASPECT_STYLES в reports/synastry/theme.py ---
AspectType = Literal["соединение", "трин", "квадрат", "секстиль", "оппозиция"]

AspectStrength = Literal["Очень сильно", "Сильно", "Заметно", "Фоновое"]

METRIC_LABELS: tuple[str, ...] = (
    "Притяжение",
    "Эмоциональный контакт",
    "Общение",
    "Долгосрочность",
)

ZONE_BLOCK_TITLES: tuple[str, ...] = (
    "Что работает само",
    "Зоны роста",
    "Опора пары",
)

NATAL_PLANET_KEYS: tuple[str, ...] = (
    "sun",
    "moon",
    "asc",
    "mercury",
    "venus",
    "mars",
    "jupiter",
    "saturn",
)


class CompatibilityPersonInput(BaseModel):
    name: str
    gender: str
    birth_date: date
    birth_time: str | None = None
    birth_place: str
    timezone: str = "Europe/Moscow"
    accuracy_tier: int = Field(ge=0, le=100)
    natal: dict[str, str]


class SynastryAspectInput(BaseModel):
    from_person: str
    from_point: str
    aspect: AspectType
    to_person: str
    to_point: str
    orb_deg: float = Field(ge=0.0, le=6.0)
    theme: str = ""


class CompatibilityPromptInput(BaseModel):
    person_a: CompatibilityPersonInput
    person_b: CompatibilityPersonInput
    aspects: list[SynastryAspectInput]
    relationship_context: Literal["love", "work", "friendship"] = "love"
    pair_mode: Literal["me_partner", "two_people"] = "me_partner"


class LlmAspectBlock(BaseModel):
    """Один аспект в PDF-карточке (strong или working)."""

    aspect_type: AspectType
    from_planet: str = Field(
        ...,
        description='Формат: «Планета · Знак», напр. «Солнце · Водолей»',
        max_length=48,
    )
    to_planet: str = Field(..., max_length=48)
    orb: str = Field(
        ...,
        description='Число орба строкой без «°», напр. «0.13»',
        max_length=8,
        pattern=r"^\d{1,2}(\.\d{1,2})?$",
    )
    strength: AspectStrength
    headline: str = Field(..., max_length=56)
    body: str = Field(..., max_length=300)


class LlmMetric(BaseModel):
    label: Literal[
        "Притяжение",
        "Эмоциональный контакт",
        "Общение",
        "Долгосрочность",
    ]
    value: float = Field(ge=0.0, le=1.0)


class LlmZoneBlock(BaseModel):
    title: Literal["Что работает само", "Зоны роста", "Опора пары"]
    items: list[str] = Field(min_length=3, max_length=5)

    @field_validator("items")
    @classmethod
    def _item_length(cls, items: list[str]) -> list[str]:
        for item in items:
            if len(item) > 110:
                msg = f"пункт зоны слишком длинный ({len(item)} симв., макс. 110)"
                raise ValueError(msg)
        return items


class CompatibilityLlmOutput(BaseModel):
    """Текстовые поля PDF — финальный контракт после assemble."""

    tldr: str = Field(..., min_length=40, max_length=340)
    pair_story: str = Field(..., min_length=120, max_length=1400)
    natal_insight: str = Field(..., min_length=30, max_length=260)
    metrics: list[LlmMetric] = Field(min_length=4, max_length=4)
    strong_aspects: list[LlmAspectBlock] = Field(min_length=1, max_length=12)
    working_aspects: list[LlmAspectBlock] = Field(min_length=0, max_length=12)
    zone_blocks: list[LlmZoneBlock] = Field(min_length=3, max_length=3)
    conclusion_quote: str = Field(..., min_length=50, max_length=420)
    conclusion_tip: str = Field(..., min_length=20, max_length=220)
    working_aspects_intro: str = Field(
        default="Орб 2–6° — требуют внимания, дают точки роста",
        max_length=90,
    )

    @field_validator("metrics")
    @classmethod
    def _metrics_order(cls, metrics: list[LlmMetric]) -> list[LlmMetric]:
        labels = [m.label for m in metrics]
        if labels != list(METRIC_LABELS):
            msg = f"metrics должны быть в порядке: {', '.join(METRIC_LABELS)}"
            raise ValueError(msg)
        return metrics

    @field_validator("zone_blocks")
    @classmethod
    def _zone_order(cls, blocks: list[LlmZoneBlock]) -> list[LlmZoneBlock]:
        titles = [b.title for b in blocks]
        if titles != list(ZONE_BLOCK_TITLES):
            msg = f"zone_blocks должны быть в порядке: {', '.join(ZONE_BLOCK_TITLES)}"
            raise ValueError(msg)
        return blocks

    @model_validator(mode="after")
    def _aspect_orb_ranges(self) -> CompatibilityLlmOutput:
        for asp in self.strong_aspects:
            orb = float(asp.orb)
            if orb >= 2.0:
                msg = f"strong_aspects: орб {asp.orb} должен быть < 2.0"
                raise ValueError(msg)
        for asp in self.working_aspects:
            orb = float(asp.orb)
            if orb < 2.0 or orb > 6.0:
                msg = f"working_aspects: орб {asp.orb} должен быть 2.0–6.0"
                raise ValueError(msg)
        return self
