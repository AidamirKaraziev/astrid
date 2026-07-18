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
    position_block,
    question_line,
    summary_block,
    title_line,
    validate_field_lengths,
)
from astra.tarot.card import TarotCard
from astra.tarot.spreads import SPREADS, SpreadType

_INTRO_MIN_LEN = 25


class ThreeCardsReading(BaseModel):
    intro: str = Field(description="слова от Астрид: тёплое вступление 1–2 предложения")
    heart: str = Field(description="суть вопроса на поверхности")
    hidden: str = Field(description="что скрыто под ситуацией")
    outcome: str = Field(description="к чему всё идёт")
    summary: str = Field(description="общий итог + одно конкретное действие")


# --- План доводки модуля «Три карты» до идеала (TODO 3: сохранить этот план) ---
# TODO 1 ✅ Жёсткая структура промпта и схемы сообщения + «слова от Астрид» (intro).
# TODO 2 ✅ Промпт переведён на английский (экономия токенов); вывод — только русский.
# TODO 3 ⏳ Держать этот план в файле; отмечать сделанные шаги.
#
# _METHOD — на английском (дешевле по токенам для DeepSeek). ВАЖНО: значения
# полей модель обязана писать по-русски (кириллицей) — это жёстко прописано.
# PERSONA (base.py) остаётся на русском: она общая для всех раскладов и русским
# контекстом дополнительно гарантирует русский ответ.
_METHOD = dedent(
    """\
    Product: the "Three Cards" spread — Heart -> Hidden Current -> Outcome.
    Not past/present/future, but three layers of ONE situation.

    CRITICAL LANGUAGE RULE: write every JSON string VALUE in RUSSIAN (Cyrillic)
    only. This is a Russian-language product. Never write values in English or
    Latin letters. Keep the JSON keys exactly as given below (in English).

    FIXED STRUCTURE. Return JSON with EXACTLY these five fields, in this order:

    1) intro (Astrid's words). The ONLY place for a warm opening: 1-2 sentences
       that set the tone and signal this spread looks BENEATH the surface of the
       question. Do not address by name; match the client's grammatical gender
       (field "пол": женщина -> feminine forms, мужчина -> masculine).
    2) heart (Сердце вопроса). The essence on the surface — what the person
       already feels and would name themselves. The core, honest and warm.
    3) hidden (Скрытое течение). The MOST valuable card: a non-obvious factor,
       a suppressed feeling, an illusion or fear the person does not notice.
       Reveal what does not lie on the surface.
    4) outcome (К чему идёт). Where the current balance of forces leads if nothing
       changes. Not a verdict, an honest vector.
    5) summary (Итог). Tie the three layers together and give ONE concrete action
       (often: how to tell the real from the imagined).

    Rules: intro is the only opening; heart/hidden/outcome contain ONLY the
    meaning of their own layer — no greetings, no name. Read each card strictly
    in its layer; the cards echo each other (hidden explains heart, outcome
    follows from both).

    JSON schema (return exactly these fields, in this order; VALUES IN RUSSIAN):
    {
      "intro": "1-2 sentences: warm opening from Astrid",
      "heart": "2-4 sentences: the essence of the question on the surface",
      "hidden": "2-4 sentences: what is hidden beneath, the non-obvious factor",
      "outcome": "2-4 sentences: where it heads at the current balance of forces",
      "summary": "1-2 sentences of conclusion + one concrete action"
    }

    How the user sees the final message (structure is fixed; the emoji and card
    names are added by us — do NOT write them yourself):
    🃏 Три карты
    [intro]
    💛 Сердце вопроса — <card>: [heart]
    🌊 Скрытое течение — <card>: [hidden]
    🔮 К чему идёт — <card>: [outcome]
    ✨ Итог: [summary]
    """,
)

SYSTEM_PROMPT = f"{PERSONA}\n\n{_METHOD}".strip()


class ThreeCardsProduct(TarotProduct):
    spread_type = SpreadType.THREE_CARDS
    spec = SPREADS[SpreadType.THREE_CARDS]
    schema = ThreeCardsReading
    system_prompt = SYSTEM_PROMPT
    max_tokens = 850

    def validate(self, data: ThreeCardsReading) -> str | None:  # type: ignore[override]
        if len(data.intro.strip()) < _INTRO_MIN_LEN:
            return "field_intro_too_short"
        return validate_field_lengths(data, ["heart", "hidden", "outcome"])

    def render(self, question: str | None, cards: list[TarotCard], data: ThreeCardsReading) -> str:  # type: ignore[override]
        # Жёсткий формат: заголовок → слова от Астрид → 3 слоя → итог.
        lines = [title_line(self.spec)]
        q_line = question_line(question)
        if q_line:
            lines.append(q_line)
        lines += ["", data.intro.strip()]
        for position, card in zip(self.spec.positions, cards, strict=True):
            lines += [
                "",
                position_block(
                    position.label_ru,
                    card,
                    getattr(data, position.key),
                    emoji=position.emoji,
                ),
            ]
        lines += ["", summary_block(data.summary)]
        return "\n".join(lines)
