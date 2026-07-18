"""Продукт «Расклад на отношения»: 5 карт о связи между двумя людьми."""

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


class RelationshipReading(BaseModel):
    you: str = Field(description="что вносишь в отношения ты")
    partner: str = Field(description="что вносит второй человек")
    between: str = Field(description="природа связи между вами")
    obstacle: str = Field(description="что мешает связи")
    direction: str = Field(description="куда движутся отношения")
    summary: str = Field(description="общий итог + одно конкретное действие")


_METHOD = dedent(
    """\
    Продукт: «Расклад на отношения» — 5 карт о связи между двумя людьми.
    Это карты об отношениях, а не синастрия: второго человека знаешь только по
    вопросу, дату рождения не выдумывай.
    Позиции: Ты → Он(а) → Между вами → Что мешает → Куда это идёт.

    Схема JSON (верни ровно эти поля):
    {
      "you": "2–3 предложения: что чувствуешь и вносишь ты",
      "partner": "2–3 предложения: что вносит второй человек",
      "between": "2–3 предложения: чем связь является на самом деле",
      "obstacle": "2–3 предложения: главное препятствие или страх",
      "direction": "2–3 предложения: куда идут отношения при текущем раскладе",
      "summary": "1–2 предложения итога + одно конкретное действие"
    }
    """,
)

SYSTEM_PROMPT = f"{PERSONA}\n\n{_METHOD}".strip()


class RelationshipProduct(TarotProduct):
    spread_type = SpreadType.RELATIONSHIP
    spec = SPREADS[SpreadType.RELATIONSHIP]
    schema = RelationshipReading
    system_prompt = SYSTEM_PROMPT
    max_tokens = 1100

    def validate(self, data: RelationshipReading) -> str | None:  # type: ignore[override]
        return validate_field_lengths(
            data, ["you", "partner", "between", "obstacle", "direction"],
        )

    def render(self, question: str | None, cards: list[TarotCard], data: RelationshipReading) -> str:  # type: ignore[override]
        return self.render_positioned(question, cards, data)
