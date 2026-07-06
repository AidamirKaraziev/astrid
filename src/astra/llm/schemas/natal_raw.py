"""Схемы сырого вывода LLM для разбора натала (Split Contract) — только смысл."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from astra.llm.schemas.compatibility_raw import AspectInterpretationRaw


def _validate_metrics(values: list[float]) -> list[float]:
    for value in values:
        if not 0.0 <= value <= 1.0:
            msg = "metrics должны быть в диапазоне 0.0–1.0"
            raise ValueError(msg)
    return values


class SphereTextRaw(BaseModel):
    text: str = Field(..., description="3–4 предложения о сфере с опорой на факторы карты")
    tip: str = Field(..., description="Один конкретный шаг, начинается с глагола")


class NatalNarrativeSkeleton(BaseModel):
    """Шаг 1: скелет разбора — центральная тема и напряжение карты."""

    core_story: str = Field(
        ...,
        description=(
            "3 абзаца через \\n\\n: как человек звучит → внутренний конфликт "
            "→ суперсила"
        ),
    )
    central_tension: str = Field(
        ..., description="Главное напряжение карты в 1–2 предложениях, с планетами"
    )
    growth_path: str = Field(..., description="Вектор роста — 1–2 предложения")
    sphere_theses: list[str] = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Тезис по сферам: призвание, отношения, ресурсы — по 1 предложению",
    )
    metrics: list[float] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="4 оценки 0.0–1.0: энергия, эмоции, коммуникация, устойчивость",
    )

    _metrics = field_validator("metrics")(_validate_metrics)


class NatalContentRaw(BaseModel):
    """Шаг 2: полный контент разбора."""

    tldr: str = Field(..., description="Краткий итог карты: 2–3 предложения, цепляет")
    core_story: str = Field(
        ..., description="Портрет: 3 абзаца через \\n\\n (уточни скелет)"
    )
    metrics: list[float] = Field(..., min_length=4, max_length=4)
    sun_text: str = Field(..., description="Солнце: ядро личности, 3–4 предложения")
    moon_text: str = Field(..., description="Луна: эмоции и потребности, 3–4 предложения")
    asc_text: str | None = Field(
        None, description="Асцендент: как видят люди (null, если время неизвестно)"
    )
    mercury_text: str = Field(..., description="Меркурий: мышление и речь")
    venus_text: str = Field(..., description="Венера: чувства и ценности")
    mars_text: str = Field(..., description="Марс: действие и воля")
    aspect_interpretations: list[AspectInterpretationRaw] = Field(
        ...,
        description="По одному объекту на каждый аспект входа, в порядке индексов [0]…[N]",
    )
    spheres: list[SphereTextRaw] = Field(
        ...,
        min_length=3,
        max_length=3,
        description="3 сферы в порядке: призвание/карьера, отношения, ресурсы/деньги",
    )
    north_node_text: str = Field(..., description="Северный узел: вектор роста")
    south_node_text: str = Field(..., description="Южный узел: привычный сценарий")
    lilith_text: str = Field(..., description="Лилит: теневая зона")
    zone_items: list[list[str]] = Field(
        ...,
        min_length=3,
        max_length=3,
        description="3 списка пунктов: сильные стороны / зоны роста / опоры",
    )
    practical_tips: list[str] = Field(
        ...,
        min_length=3,
        max_length=5,
        description="3–5 конкретных действий на неделю, каждое с глагола",
    )
    balance_note: str = Field(
        ..., description="Комментарий к балансу стихий и крестов, 2 предложения"
    )
    conclusion_quote: str = Field(..., description="Итоговая мысль карты, 2–3 предложения")
    conclusion_tip: str = Field(..., description="Практика на неделю — одно действие")

    _metrics = field_validator("metrics")(_validate_metrics)

    @field_validator("zone_items")
    @classmethod
    def _zone_sizes(cls, blocks: list[list[str]]) -> list[list[str]]:
        for block in blocks:
            if not 3 <= len(block) <= 5:
                msg = "в каждом zone_items нужно 3–5 пунктов"
                raise ValueError(msg)
        return blocks


class NatalPolishRaw(BaseModel):
    """Шаг 3: редактор — вычистить клише и Barnum-фразы, усилить конкретику."""

    tldr: str
    core_story: str
    sun_text: str
    moon_text: str
    asc_text: str | None = None
    mercury_text: str
    venus_text: str
    mars_text: str
    aspect_interpretations: list[AspectInterpretationRaw]
    spheres: list[SphereTextRaw] = Field(..., min_length=3, max_length=3)
    north_node_text: str
    south_node_text: str
    lilith_text: str
    balance_note: str
    conclusion_quote: str
    conclusion_tip: str
