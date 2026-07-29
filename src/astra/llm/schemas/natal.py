"""Схемы ввода/вывода для промпта натала → PDF натальной карты."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from astra.llm.schemas.compatibility import MAX_ASPECT_BLOCKS, AspectType, LlmAspectBlock

NATAL_METRIC_LABELS: tuple[str, ...] = (
    "Энергия",
    "Эмоции",
    "Коммуникация",
    "Устойчивость",
)

NATAL_ZONE_TITLES: tuple[str, ...] = (
    "Сильные стороны",
    "Зоны роста",
    "Опоры",
)

NATAL_SPHERE_TITLES: tuple[str, ...] = (
    "Призвание и карьера",
    "Отношения",
    "Ресурсы и деньги",
)

# сколько аспектов (топ по орбу) отдаём LLM на интерпретацию
NATAL_ASPECTS_LIMIT = 12


class NatalPersonInput(BaseModel):
    name: str
    gender: str | None = None
    birth_date: date
    birth_time: str | None = None
    birth_place: str
    timezone: str = "Europe/Moscow"
    has_time: bool


class NatalPointInput(BaseModel):
    """Точка карты для промпта: все факты предвычислены."""

    key: str  # en-ключ: "Sun", "Chiron", "True_North_Lunar_Node"
    name: str  # по-русски
    sign: str
    sign_deg: float
    house: int | None = None
    retrograde: bool = False
    dignity: str | None = None


class NatalAspectPromptInput(BaseModel):
    p1_key: str
    p1: str  # по-русски
    p2_key: str
    p2: str
    aspect: AspectType
    orb_deg: float = Field(ge=0.0, le=8.0)


class NatalPromptInput(BaseModel):
    person: NatalPersonInput
    points: list[NatalPointInput]
    asc_sign: str | None = None
    mc_sign: str | None = None
    aspects: list[NatalAspectPromptInput]  # отсортированы по орбу, топ-12
    feature_lines: list[str] = Field(
        default_factory=list,
        description="Предвычисленные акценты карты (доминанты, стеллиумы, конфигурации)",
    )
    element_balance: dict[str, float] = Field(default_factory=dict)
    modality_balance: dict[str, float] = Field(default_factory=dict)
    moon_phase: str | None = None
    moon_sign_uncertain: bool = False

    def point(self, key: str) -> NatalPointInput | None:
        return next((p for p in self.points if p.key == key), None)


class NatalPlanetText(BaseModel):
    """Карточка планеты в PDF: факты собирает код, LLM даёт только текст."""

    point_key: str
    title: str = Field(..., max_length=64)  # «Солнце в Близнецах · 9 дом»
    caption: str = Field(default="", max_length=48)  # «ретроградный · обитель»
    text: str = Field(..., min_length=40, max_length=450)


class NatalSphereBlock(BaseModel):
    title: Literal["Призвание и карьера", "Отношения", "Ресурсы и деньги"]
    factors: str = Field(..., max_length=90)  # «MC в Раке · Юпитер в 10 доме»
    text: str = Field(..., min_length=60, max_length=520)
    tip: str = Field(..., min_length=15, max_length=180)


class NatalMetric(BaseModel):
    label: Literal["Энергия", "Эмоции", "Коммуникация", "Устойчивость"]
    value: float = Field(ge=0.0, le=1.0)


class NatalZoneBlock(BaseModel):
    title: Literal["Сильные стороны", "Зоны роста", "Опоры"]
    items: list[str] = Field(min_length=3, max_length=5)

    @field_validator("items")
    @classmethod
    def _item_length(cls, items: list[str]) -> list[str]:
        for item in items:
            if len(item) > 110:
                msg = f"пункт зоны слишком длинный ({len(item)} симв., макс. 110)"
                raise ValueError(msg)
        return items


class NatalLlmOutput(BaseModel):
    """Финальный контракт разбора натала после assemble."""

    tldr: str = Field(..., min_length=40, max_length=340)
    core_story: str = Field(..., min_length=120, max_length=1400)
    metrics: list[NatalMetric] = Field(min_length=4, max_length=4)
    personality: list[NatalPlanetText] = Field(min_length=2, max_length=3)
    mind_feelings_action: list[NatalPlanetText] = Field(min_length=3, max_length=3)
    strong_aspects: list[LlmAspectBlock] = Field(min_length=0, max_length=MAX_ASPECT_BLOCKS)
    working_aspects: list[LlmAspectBlock] = Field(min_length=0, max_length=MAX_ASPECT_BLOCKS)
    spheres: list[NatalSphereBlock] = Field(min_length=3, max_length=3)
    karmic: list[NatalPlanetText] = Field(min_length=2, max_length=3)
    zone_blocks: list[NatalZoneBlock] = Field(min_length=3, max_length=3)
    practical_tips: list[str] = Field(min_length=3, max_length=5)
    balance_note: str = Field(default="", max_length=280)
    accuracy_note: str = Field(default="", max_length=220)
    conclusion_quote: str = Field(..., min_length=50, max_length=420)
    conclusion_tip: str = Field(..., min_length=20, max_length=220)

    @field_validator("metrics")
    @classmethod
    def _metrics_order(cls, metrics: list[NatalMetric]) -> list[NatalMetric]:
        labels = [m.label for m in metrics]
        if labels != list(NATAL_METRIC_LABELS):
            msg = f"metrics должны быть в порядке: {', '.join(NATAL_METRIC_LABELS)}"
            raise ValueError(msg)
        return metrics

    @field_validator("zone_blocks")
    @classmethod
    def _zone_order(cls, blocks: list[NatalZoneBlock]) -> list[NatalZoneBlock]:
        titles = [b.title for b in blocks]
        if titles != list(NATAL_ZONE_TITLES):
            msg = f"zone_blocks должны быть в порядке: {', '.join(NATAL_ZONE_TITLES)}"
            raise ValueError(msg)
        return blocks

    @field_validator("spheres")
    @classmethod
    def _sphere_order(cls, blocks: list[NatalSphereBlock]) -> list[NatalSphereBlock]:
        titles = [b.title for b in blocks]
        if titles != list(NATAL_SPHERE_TITLES):
            msg = f"spheres должны быть в порядке: {', '.join(NATAL_SPHERE_TITLES)}"
            raise ValueError(msg)
        return blocks

    @field_validator("practical_tips")
    @classmethod
    def _tip_length(cls, tips: list[str]) -> list[str]:
        for tip in tips:
            if len(tip) > 200:
                msg = f"совет слишком длинный ({len(tip)} симв., макс. 200)"
                raise ValueError(msg)
        return tips

    @model_validator(mode="after")
    def _aspect_orb_ranges(self) -> NatalLlmOutput:
        for asp in self.strong_aspects:
            if float(asp.orb) >= 2.0:
                msg = f"strong_aspects: орб {asp.orb} должен быть < 2.0"
                raise ValueError(msg)
        for asp in self.working_aspects:
            orb = float(asp.orb)
            if orb < 2.0 or orb > 8.0:
                msg = f"working_aspects: орб {asp.orb} должен быть 2.0–8.0"
                raise ValueError(msg)
        return self
