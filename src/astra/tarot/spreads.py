"""Спецификации раскладов: позиции и их смысл — источник правды для промпта и UI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SpreadType(StrEnum):
    YES_NO = "yes_no"
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
    SpreadType.YES_NO: SpreadSpec(
        type=SpreadType.YES_NO,
        title_ru="Расклад на решение",
        emoji="⚖️",
        positions=(
            SpreadPosition(
                key="answer",
                label_ru="Ответ",
                meaning="карта отвечает на вопрос да или нет и объясняет цену этого ответа",
            ),
        ),
        question_required=True,
        question_hint=(
            "Сформулируй вопрос так, чтобы на него можно было ответить «да» или «нет».\n"
            "Например: «Стоит ли мне соглашаться на эту работу?»"
        ),
        max_tokens=400,
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
        positions=(
            SpreadPosition(
                key="you",
                label_ru="Ты",
                meaning="что чувствуешь и вносишь в отношения ты",
            ),
            SpreadPosition(
                key="partner",
                label_ru="Он(а)",
                meaning="что чувствует и вносит второй человек",
            ),
            SpreadPosition(
                key="between",
                label_ru="Между вами",
                meaning="природа связи, чем эти отношения являются на самом деле",
            ),
            SpreadPosition(
                key="obstacle",
                label_ru="Что мешает",
                meaning="главное препятствие или страх, который тормозит связь",
            ),
            SpreadPosition(
                key="direction",
                label_ru="Куда это идёт",
                meaning="вектор развития отношений при текущем раскладе сил",
            ),
        ),
        question_required=True,
        question_hint=(
            "О ком или о каких отношениях спросим карты?\n"
            "Например: «Что происходит между мной и Сашей?»"
        ),
        max_tokens=1000,
    ),
}
