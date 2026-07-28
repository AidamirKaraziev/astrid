"""Схемы продуктов раздела «Спроси Астрид».

Общий контракт всех вопросов: Python считает факты и числа детерминированно,
LLM их только объясняет. Поэтому у каждого продукта есть свой `*Result` —
воспроизводимый снимок расчёта, который кладётся в БД вместе с ответом.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class PartnershipWindow(BaseModel):
    """Окно активации партнёрства: транзит медленной планеты к точке карты."""

    start: date
    peak: date
    end: date
    transit: str  # «Сатурн», «Юпитер», «Уран»
    target: str  # «десцендент», «Венера», «управитель 7 дома»
    weight: float  # вклад окна: чем выше, тем крупнее история
    age: int  # возраст человека на пике окна


class FatedPartnersFactors(BaseModel):
    """Факторы карты, из которых выведено число. Идут в промпт как есть.

    LLM обязана называть их вслух — иначе ответ скатывается в гороскоп из паблика.
    """

    has_time: bool
    dsc_sign: str | None = None
    dsc_modality: str | None = None
    double_bodied_dsc: bool = False
    planets_in_seventh: list[str] = Field(default_factory=list)
    ruler_seventh: str | None = None
    ruler_seventh_sign: str | None = None
    ruler_seventh_modality: str | None = None
    ruler_seventh_aspects: list[str] = Field(default_factory=list)
    venus_sign: str | None = None
    venus_modality: str | None = None
    venus_retrograde: bool = False
    venus_aspects: list[str] = Field(default_factory=list)
    north_node_house: int | None = None
    score: float = 0.0
    notes: list[str] = Field(default_factory=list)  # человеческие формулировки для промпта


class FatedPartnersResult(BaseModel):
    """Ответ расчёта: два числа + чем они обоснованы."""

    methodology_version: int
    total: int
    past: int
    future: int
    age: int
    in_relationship: bool
    factors: FatedPartnersFactors
    windows_past: list[PartnershipWindow] = Field(default_factory=list)
    windows_future: list[PartnershipWindow] = Field(default_factory=list)
