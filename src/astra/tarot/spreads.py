"""Спецификации раскладов: позиции и их смысл — источник правды для промпта и UI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SpreadType(StrEnum):
    WISH = "wish"
    THREE_CARDS = "three_cards"
    RELATIONSHIP = "relationship"


@dataclass(frozen=True, slots=True)
class SpreadPosition:
    key: str
    label_ru: str
    meaning: str  # что эта позиция значит — уходит в промпт
    emoji: str = ""  # тематическое эмодзи позиции; пусто — берём эмодзи карты


@dataclass(frozen=True, slots=True)
class SpreadSpec:
    type: SpreadType
    title_ru: str
    emoji: str
    positions: tuple[SpreadPosition, ...]
    question_required: bool
    question_hint: str  # подсказка пользователю при вводе вопроса
    max_tokens: int

    @property
    def card_count(self) -> int:
        return len(self.positions)


SPREADS: dict[SpreadType, SpreadSpec] = {
    SpreadType.WISH: SpreadSpec(
        type=SpreadType.WISH,
        title_ru="Загадай желание",
        emoji="🌟",
        # Компактный ритуал: 3 карты + честный вердикт «сбудется ли» + срок.
        positions=(
            SpreadPosition(
                key="heart",
                label_ru="Сердце желания",
                emoji="💫",
                meaning="суть желания глазами карт — что человек хочет на самом деле",
            ),
            SpreadPosition(
                key="path",
                label_ru="Что на пути",
                emoji="🛤",
                meaning="что помогает и что мешает желанию сбыться прямо сейчас",
            ),
            SpreadPosition(
                key="outcome",
                label_ru="К чему идёт",
                emoji="🌙",
                meaning="сбудется ли желание при нынешнем раскладе сил и с какой ценой",
            ),
        ),
        question_required=True,
        question_hint=(
            "Загадай желание — опиши его одним-двумя предложениями.\n"
            "Например: «Хочу, чтобы мы с Сашей снова были вместе»."
        ),
        max_tokens=700,
    ),
    SpreadType.THREE_CARDS: SpreadSpec(
        type=SpreadType.THREE_CARDS,
        title_ru="Три карты",
        emoji="🃏",
        positions=(
            SpreadPosition(
                key="heart",
                label_ru="Сердце вопроса",
                emoji="💛",
                meaning=(
                    "суть на поверхности — что человек уже чувствует и назвал бы сам, "
                    "явное ядро ситуации"
                ),
            ),
            SpreadPosition(
                key="hidden",
                label_ru="Скрытое течение",
                emoji="🌊",
                meaning=(
                    "что скрыто под ситуацией — неочевидный фактор, подавленное чувство, "
                    "иллюзия или страх, который человек не замечает"
                ),
            ),
            SpreadPosition(
                key="outcome",
                label_ru="К чему идёт",
                emoji="🔮",
                meaning="вероятный исход при нынешнем раскладе сил, если ничего не менять",
            ),
        ),
        question_required=False,
        question_hint=(
            "О чём спросить карты? Опиши ситуацию одним-двумя предложениями —\n"
            "или нажми «⏭ Пропустить», и карты заглянут в суть твоего дня."
        ),
        max_tokens=750,
    ),
    SpreadType.RELATIONSHIP: SpreadSpec(
        type=SpreadType.RELATIONSHIP,
        title_ru="Расклад на отношения",
        emoji="💕",
        # Фреймворк «Что он/она чувствует»: центр — внутренний мир второго
        # человека и связь, а не синастрия. Ключевая карта — «unspoken».
        positions=(
            SpreadPosition(
                key="who_you_are",
                label_ru="Кто ты для него(неё)",
                emoji="👤",
                meaning=(
                    "какое место ты занимаешь в жизни и чувствах второго человека "
                    "прямо сейчас"
                ),
            ),
            SpreadPosition(
                key="unspoken",
                label_ru="Что чувствует, но молчит",
                emoji="🌊",
                meaning=(
                    "самое ценное: что второй человек чувствует к тебе, но не "
                    "произносит вслух — подавленное, скрытое или ещё не осознанное"
                ),
            ),
            SpreadPosition(
                key="holding_back",
                label_ru="Что его(её) останавливает",
                emoji="⛔️",
                meaning=(
                    "что удерживает второго от того, чтобы открыться или сделать шаг "
                    "— страх, привычка, прошлый опыт или обстоятельства"
                ),
            ),
            SpreadPosition(
                key="what_wants",
                label_ru="Чего хочет на самом деле",
                emoji="💗",
                meaning=(
                    "чего второй человек на самом деле хочет от этой связи — за "
                    "словами и поведением"
                ),
            ),
            SpreadPosition(
                key="your_move",
                label_ru="Твой ход",
                emoji="➡️",
                meaning=(
                    "что в твоих силах сделать с этим — честный практичный шаг, а не "
                    "ожидание"
                ),
            ),
        ),
        question_required=True,
        question_hint=(
            "О ком спросим карты? Опиши, кто этот человек и что между вами.\n"
            "Например: «Что чувствует ко мне Саша?»"
        ),
        max_tokens=1150,
    ),
}
