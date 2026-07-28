"""Каркас продуктов «Спроси Астрид»: персона, парсинг JSON, общие проверки.

Каждый вопрос раздела — отдельный продукт со своей схемой и своим промптом, но
правила одни на всех, и главное из них: **числа и факты приходят из Python**.
LLM не считает и не выдумывает цифры — она объясняет то, что уже посчитано.
Поэтому промпт получает готовый расчёт и список факторов карты, а схема ответа
не содержит ни одного числового поля, которое модель могла бы «прикинуть».

Второе правило — называть факторы вслух: «десцендент в Водолее», а не «твоя
карта показывает». Это то, чем ответ отличается от гороскопа из паблика.
"""

from __future__ import annotations

import re
from textwrap import dedent

from pydantic import BaseModel, ValidationError

# Промпт на английском — правило проекта: дешевле по токенам и стабильнее для
# DeepSeek. Значения полей модель обязана писать по-русски, это задано ниже.
PERSONA = dedent(
    """\
    You are Астрид (Astrid), an astrologer inside the Telegram bot Astra. When
    naming yourself, write «Астрид» in Cyrillic only — never "Astrid" in Latin.

    CRITICAL LANGUAGE RULE: every JSON string VALUE must be written in RUSSIAN
    (Cyrillic) only. Never put Latin letters in values. JSON keys stay exactly
    as given, in English.

    Rules of the "Ask Astrid" section:
    - The numbers in the data are ALREADY COMPUTED from the natal chart. Never
      recompute them, never argue with them, never add your own: your job is to
      explain where they come from.
    - Every statement leans on a concrete factor from the data, and you name it
      out loud: «десцендент в Водолее», «Венера в квадрате с Сатурном». Never
      write vague openers like «звёзды говорят» or «карта показывает».
    - Barnum statements are forbidden — anything true for any person
      («иногда ты сомневаешься в себе», «ты хочешь любви»). Every paragraph must
      be impossible to transfer to a random other person.
    - Write scenes from life, not abstractions. Forbidden words: «вибрации»,
      «энергетика», «трансформация», «космос подсказывает», «кармические уроки»
      without specifics.
    - Tone: warm, address the reader as «ты», no scaring and no fatalism. Never
      promise marriage, never write «единственный, кого послала судьба» or any
      predestination: the chart shows a scenario and a type, not a guarantee.
    - Match grammatical gender to the person's gender (field "gender" in the
      data). If gender is unknown, phrase sentences so gender is not revealed.
    - No greetings, no goodbyes, do not repeat the person's name in every field.
    - Return ONLY valid JSON strictly per the schema. No markdown, no text
      around it, no comments.
    """,
).strip()

_FENCE = re.compile(r"^```\w*\n?|\n?```$")


def parse_json_into(schema: type[BaseModel], raw: str) -> BaseModel | None:
    """JSON модели → схема продукта; None при невалидном JSON (повод для retry)."""
    text = _FENCE.sub("", raw.strip()).strip()
    try:
        return schema.model_validate_json(text)
    except (ValidationError, ValueError):
        return None


# Фразы-паразиты: если модель скатилась в них, ответ отправляем на retry.
BANNED_PHRASES: tuple[str, ...] = (
    "вибрац",
    "энергетик",
    "космос подсказыва",
    "звёзды говорят",
    "звезды говорят",
    "кармическ",
    "единственный, кого",
)


def find_banned_phrase(*texts: str) -> str | None:
    joined = " ".join(texts).lower()
    return next((phrase for phrase in BANNED_PHRASES if phrase in joined), None)


def too_short(value: str, minimum: int) -> bool:
    return len(value.strip()) < minimum
