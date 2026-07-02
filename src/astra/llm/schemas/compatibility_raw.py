"""Схемы сырого вывода LLM (Split Contract) — только смысл, без структуры PDF."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class AspectInterpretationRaw(BaseModel):
    headline: str = Field(..., description="Заголовок карточки аспекта, до 56 символов")
    body: str = Field(
        ...,
        description="2–3 предложения: наблюдение + что это значит в жизни пары",
    )


class CompatibilityNarrativeSkeleton(BaseModel):
    """Шаг 1: скелет нарратива."""

    pair_story: str = Field(
        ...,
        description="3 абзаца через \\n\\n: как пара звучит вместе, конфликт, сильная сторона",
    )
    central_tension: str = Field(..., description="Главное напряжение пары в 1–2 предложениях")
    growth_path: str = Field(..., description="Куда расти паре — 1–2 предложения")
    metrics: list[float] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="4 оценки 0.0–1.0: притяжение, эмоции, общение, долгосрочность",
    )

    @field_validator("metrics")
    @classmethod
    def _metrics_range(cls, values: list[float]) -> list[float]:
        for value in values:
            if not 0.0 <= value <= 1.0:
                msg = "metrics должны быть в диапазоне 0.0–1.0"
                raise ValueError(msg)
        return values


class CompatibilityContentRaw(BaseModel):
    """Шаг 2: полный контент по аспектам и блокам."""

    tldr: str = Field(..., description="Краткий итог: 2–3 предложения")
    pair_story: str = Field(
        ...,
        description="История пары: 3 абзаца через \\n\\n (можно уточнить скелет)",
    )
    natal_insight: str = Field(..., description="Сочетание натальных карт, 2–3 предложения")
    metrics: list[float] = Field(..., min_length=4, max_length=4)
    aspect_interpretations: list[AspectInterpretationRaw] = Field(
        ...,
        description="По одному объекту на каждый аспект входа, в порядке индексов [0]…[N]",
    )
    zone_items: list[list[str]] = Field(
        ...,
        min_length=3,
        max_length=3,
        description="3 списка пунктов: что работает / зоны роста / опора пары",
    )
    conclusion_quote: str = Field(..., description="Итоговая цитата, 2–3 предложения")
    conclusion_tip: str = Field(..., description="Практика на неделю — одно конкретное действие")

    @field_validator("metrics")
    @classmethod
    def _metrics_range(cls, values: list[float]) -> list[float]:
        for value in values:
            if not 0.0 <= value <= 1.0:
                msg = "metrics должны быть в диапазоне 0.0–1.0"
                raise ValueError(msg)
        return values

    @field_validator("zone_items")
    @classmethod
    def _zone_sizes(cls, blocks: list[list[str]]) -> list[list[str]]:
        for block in blocks:
            if not 3 <= len(block) <= 5:
                msg = "в каждом zone_items нужно 3–5 пунктов"
                raise ValueError(msg)
        return blocks


class CompatibilityPolishRaw(BaseModel):
    """Шаг 3: редактор — вычистить клише, выровнять тон."""

    tldr: str
    pair_story: str
    natal_insight: str
    conclusion_quote: str
    conclusion_tip: str
    aspect_interpretations: list[AspectInterpretationRaw]
