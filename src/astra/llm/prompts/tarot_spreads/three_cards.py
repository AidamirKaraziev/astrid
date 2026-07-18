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
# TODO 2 ⏳ После одобрения промпта — перевести его на английский язык.
# TODO 3 ⏳ Держать этот план в файле; отмечать сделанные шаги.
_METHOD = dedent(
    """\
    Продукт: «Три карты» в раскладе Сердце → Скрытое течение → Исход.
    Это НЕ прошлое-настоящее-будущее, а три слоя одной ситуации.

    ЖЁСТКАЯ СТРУКТУРА. Верни JSON РОВНО с пятью полями в этом порядке:

    1) intro (слова от Астрид). ЕДИНСТВЕННОЕ место для тёплого вступления: 1–2
       предложения, которыми ты настраиваешь человека и обозначаешь, что этот
       расклад заглядывает ПОД поверхность вопроса. Без обращения по имени, с
       учётом пола. Пример тона: «Давай посмотрим глубже. Карты показывают не
       только то, что на виду, но и то, что ты пока не назвала словами.»
    2) heart (Сердце вопроса). Суть на поверхности — то, что человек уже
       чувствует и назвал бы сам. Ядро ситуации, честно и тепло.
    3) hidden (Скрытое течение). САМАЯ ценная карта: неочевидный фактор,
       подавленное чувство, иллюзия или страх, которого человек не замечает.
       Здесь ты открываешь то, что не лежит на поверхности.
    4) outcome (К чему идёт). Куда ведёт нынешний расклад сил, если ничего не
       менять. Не приговор, а честный вектор.
    5) summary (Итог). Свяжи три слоя и дай ОДНО конкретное действие (часто —
       как отделить реальное от выдуманного).

    Правила: intro — единственное вступление; heart/hidden/outcome содержат
    ТОЛЬКО смысл своей позиции, без приветствий и без имени. Каждую карту читай
    строго в её слое; карты перекликаются — скрытое объясняет сердце, исход
    вытекает из обоих.

    Схема JSON (верни ровно эти поля, ровно в этом порядке):
    {
      "intro": "1–2 предложения: тёплое вступление от Астрид",
      "heart": "2–4 предложения: суть вопроса на поверхности",
      "hidden": "2–4 предложения: что скрыто под ситуацией, неочевидный фактор",
      "outcome": "2–4 предложения: к чему всё идёт при нынешнем раскладе",
      "summary": "1–2 предложения итога + одно конкретное действие"
    }

    Как человек увидит сообщение (структура фиксирована, эмодзи и названия карт
    подставляем мы — тебе их писать не нужно):
    🃏 Три карты
    [intro]
    💛 Сердце вопроса — <карта>: [heart]
    🌊 Скрытое течение — <карта>: [hidden]
    🔮 К чему идёт — <карта>: [outcome]
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
