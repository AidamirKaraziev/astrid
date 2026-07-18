"""Продукт «Три карты»: Прошлое → Настоящее → Будущее ситуации."""

from __future__ import annotations

from textwrap import dedent

from pydantic import BaseModel, Field

from astra.llm.prompts.tarot_spreads.base import (
    PERSONA,
    TarotProduct,
    validate_field_lengths,
)
from astra.tarot.card import TarotCard
from astra.tarot.spreads import SPREADS, SpreadType


class ThreeCardsReading(BaseModel):
    past: str = Field(description="карта прошлого в её позиции")
    present: str = Field(description="карта настоящего в её позиции")
    future: str = Field(description="карта будущего в её позиции")
    summary: str = Field(description="общий итог + одно конкретное действие")


_METHOD = dedent(
    """\
    Продукт: «Три карты» — история ситуации во времени.
    Прошлое (корень) → Настоящее (текущая сила) → Будущее (куда движется).
    Каждую карту читай СТРОГО в её позиции; в summary свяжи три карты вместе.

    Схема JSON (верни ровно эти поля):
    {
      "past": "2–4 предложения о карте прошлого — что привело к ситуации",
      "present": "2–4 предложения о карте настоящего — что происходит сейчас",
      "future": "2–4 предложения о карте будущего — куда всё движется",
      "summary": "1–2 предложения итога + одно конкретное действие"
    }
    """,
)

SYSTEM_PROMPT = f"{PERSONA}\n\n{_METHOD}".strip()


class ThreeCardsProduct(TarotProduct):
    spread_type = SpreadType.THREE_CARDS
    spec = SPREADS[SpreadType.THREE_CARDS]
    schema = ThreeCardsReading
    system_prompt = SYSTEM_PROMPT
    max_tokens = 750

    def validate(self, data: ThreeCardsReading) -> str | None:  # type: ignore[override]
        return validate_field_lengths(data, ["past", "present", "future"])

    def render(self, question: str | None, cards: list[TarotCard], data: ThreeCardsReading) -> str:  # type: ignore[override]
        return self.render_positioned(question, cards, data)
