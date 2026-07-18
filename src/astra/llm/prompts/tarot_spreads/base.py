"""Общий каркас продуктов таро: персона, сборка запроса, парсинг JSON, рендер.

Каждый расклад — отдельный продукт (свой промпт, своя схема, свой формат), но
персона Астрид и формат данных общие — их держим здесь, чтобы не дублировать.
Вывод модели — СТРУКТУРИРОВАННЫЙ JSON (поле на позицию), поэтому сшить текст с
неправильной позицией физически невозможно (в отличие от парсинга абзацев).
"""

from __future__ import annotations

import html
import json
import re
from abc import ABC, abstractmethod
from textwrap import dedent

from pydantic import BaseModel, ValidationError

from astra.tarot.card import TarotCard
from astra.tarot.spreads import SpreadSpec, SpreadType

PERSONA = dedent(
    """\
    Ты — Астрид, тёплый и честный таролог в Telegram-боте Astra. Если называешь
    себя — только «Астрид» (кириллицей), никогда «Astrid».

    Общие правила для любого расклада:
    - Читай каждую карту через смысл её позиции и вопрос человека, а не как
      абстрактное значение. Не пересказывай ключевые слова — прикладывай карту
      к конкретной ситуации.
    - Карты перекликаются между собой: замечай связи и противоречия.
    - Тон тёплый, обращение на «ты», без запугивания и фатализма.
    - Согласуй род с полом клиента (поле «пол» в данных): женщине — «ты готова»,
      «сама», «уверена»; мужчине — «ты готов», «сам», «уверен». Пол не указан —
      строй фразы так, чтобы не выдавать род.
    - НЕ обращайся к человеку по имени, НЕ пиши приветствий и вступлений. Имя в
      данных — только для контекста. Каждое поле схемы содержит ТОЛЬКО смысл этой
      позиции, без «смотри, что вышло» и подобного.
    - Запрещено: «вибрации», «энергетика», «трансформация», «космос подсказывает»,
      «карты никогда не ошибаются».
    - Верни ТОЛЬКО валидный JSON строго по схеме из инструкции ниже. Без markdown,
      без текста вокруг, без комментариев.
    """,
).strip()

_FENCE = re.compile(r"^```\w*\n?|\n?```$")

# Минимальные длины (символы) — защита от «пустых» полей LLM.
MIN_FIELD_LEN = 40
MIN_SUMMARY_LEN = 25


def _cards_payload(spec: SpreadSpec, cards: list[TarotCard]) -> list[dict]:
    return [
        {
            "поле": position.key,
            "позиция": position.label_ru,
            "смысл_позиции": position.meaning,
            "карта": card.name_ru,
            "ключи": list(card.keywords),
            "астро_соответствие": card.astro_affinity,
            "голос_карты": card.voice,
        }
        for position, card in zip(spec.positions, cards, strict=True)
    ]


# --- рендер-хелперы (общий язык оформления сообщений) --------------------------


def title_line(spec: SpreadSpec) -> str:
    return f"{spec.emoji} <b>{spec.title_ru}</b>"


def question_line(question: str | None) -> str | None:
    return f"<i>«{html.escape(question)}»</i>" if question else None


def position_block(label_ru: str, card: TarotCard, text: str) -> str:
    return f"{card.emoji} <b>{label_ru} — {card.name_ru}</b>\n{text.strip()}"


def summary_block(summary: str) -> str:
    return f"✨ <b>Итог:</b> {summary.strip()}"


def validate_field_lengths(data: BaseModel, field_names: list[str]) -> str | None:
    for name in field_names:
        if len(str(getattr(data, name, "")).strip()) < MIN_FIELD_LEN:
            return f"field_{name}_too_short"
    if len(str(getattr(data, "summary", "")).strip()) < MIN_SUMMARY_LEN:
        return "summary_too_short"
    return None


class TarotProduct(ABC):
    """Один продукт-расклад: свой system_prompt, схема, валидация и формат."""

    spread_type: SpreadType
    spec: SpreadSpec
    schema: type[BaseModel]
    system_prompt: str
    max_tokens: int

    def build_user_message(
        self,
        question: str | None,
        cards: list[TarotCard],
        *,
        user_name: str | None = None,
        gender: str | None = None,
    ) -> str:
        payload: dict = {}
        client: dict = {}
        if user_name:
            client["имя"] = user_name  # только контекст, обращаться по имени нельзя
        if gender:
            client["пол"] = gender
        if client:
            payload["клиент"] = client
        payload["вопрос"] = question or "вопрос не задан — прочитай расклад о дне человека"
        payload["карты"] = _cards_payload(self.spec, cards)
        return "Данные расклада:\n\n" + json.dumps(payload, ensure_ascii=False, indent=2)

    def parse(self, raw: str) -> BaseModel | None:
        """JSON → схема продукта; None при невалидном JSON (повод для retry)."""
        text = _FENCE.sub("", raw.strip()).strip()
        try:
            return self.schema.model_validate_json(text)
        except (ValidationError, ValueError):
            return None

    def render_positioned(
        self,
        question: str | None,
        cards: list[TarotCard],
        data: BaseModel,
    ) -> str:
        """Общий формат: заголовок, вопрос, блок на позицию (поле = position.key), итог."""
        lines = [title_line(self.spec)]
        q_line = question_line(question)
        if q_line:
            lines.append(q_line)
        for position, card in zip(self.spec.positions, cards, strict=True):
            lines += ["", position_block(position.label_ru, card, getattr(data, position.key))]
        lines += ["", summary_block(data.summary)]  # type: ignore[attr-defined]
        return "\n".join(lines)

    @abstractmethod
    def validate(self, data: BaseModel) -> str | None:
        """None — валидно, иначе причина для retry."""

    @abstractmethod
    def render(self, question: str | None, cards: list[TarotCard], data: BaseModel) -> str:
        """Готовое HTML-сообщение из структурированных полей."""
