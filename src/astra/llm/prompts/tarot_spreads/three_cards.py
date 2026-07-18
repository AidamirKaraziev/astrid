"""Продукт «Три карты» в раскладе Сердце → Скрытое течение → Исход.

Это не линия времени, а глубинный срез одной ситуации: что на поверхности,
что скрыто под ней, и к чему всё идёт. У каждой позиции своя чёткая роль.
"""

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
    heart: str = Field(description="суть вопроса на поверхности")
    hidden: str = Field(description="что скрыто под ситуацией")
    outcome: str = Field(description="к чему всё идёт")
    summary: str = Field(description="общий итог + одно конкретное действие")


_METHOD = dedent(
    """\
    Продукт: «Три карты» в раскладе Сердце → Скрытое течение → Исход.
    Это НЕ прошлое-настоящее-будущее, а три слоя одной ситуации:

    - heart (Сердце вопроса): суть на поверхности — то, что человек уже чувствует
      и назвал бы сам. Назови ядро ситуации честно и тепло.
    - hidden (Скрытое течение): САМАЯ ценная карта. Что скрыто под ситуацией —
      неочевидный фактор, подавленное чувство, иллюзия или страх, которого человек
      не замечает. Здесь ты открываешь то, что не лежит на поверхности.
    - outcome (К чему идёт): куда ведёт нынешний расклад сил, если ничего не менять.
      Не приговор, а честный вектор.

    Каждую карту читай СТРОГО в её слое; карты должны перекликаться — скрытое
    объясняет сердце, исход вытекает из обоих. В summary свяжи три слоя и дай одно
    конкретное действие (часто — как отделить реальное от выдуманного).

    Схема JSON (верни ровно эти поля):
    {
      "heart": "2–4 предложения: суть вопроса на поверхности",
      "hidden": "2–4 предложения: что скрыто под ситуацией, неочевидный фактор",
      "outcome": "2–4 предложения: к чему всё идёт при нынешнем раскладе",
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
    max_tokens = 800

    def validate(self, data: ThreeCardsReading) -> str | None:  # type: ignore[override]
        return validate_field_lengths(data, ["heart", "hidden", "outcome"])

    def render(self, question: str | None, cards: list[TarotCard], data: ThreeCardsReading) -> str:  # type: ignore[override]
        return self.render_positioned(question, cards, data)
