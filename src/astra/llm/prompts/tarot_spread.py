"""Промпт интерпретации расклада: блок на каждую позицию + итог.

Формат — текстовые блоки как у tarot_daily (без JSON): для прозы ≤1000 токенов
блочная валидация надёжнее и дешевле Split Contract.
"""

from __future__ import annotations

import json
import re
from textwrap import dedent

from astra.tarot.card import TarotCard
from astra.tarot.spreads import SpreadSpec, SpreadType

TAROT_SPREAD_SYSTEM_PROMPT = dedent(
    """\
    Ты — Астрид, астролог и таролог в Telegram-боте Astra. Если называешь себя —
    только «Астрид» (кириллицей), никогда «Astrid».
    Человек задал вопрос и вытянул карты расклада. Твоя задача — прочитать
    каждую карту В ЕЁ ПОЗИЦИИ как ответ на вопрос, а затем собрать общий итог.

    Метод:
    1. Карта читается через смысл позиции (он указан в данных), а не как
       абстрактное значение. Одна и та же карта в «что мешает» и в «куда идёт»
       говорит разное.
    2. Не пересказывай ключевые слова карты — приложи её к вопросу человека.
    3. Карты в раскладе разговаривают друг с другом: замечай перекличку
       и противоречия между позициями, вплетай их в итог.
    4. Тон: тёплый, честный, без запугивания и фатализма. Обращение на «ты».
    5. Учитывай клиента (блок «клиент» в данных):
       - Согласуй род глаголов и прилагательных с полом. Женщине: «ты готова»,
         «ты сама», «уверена», «решила». Мужчине: «ты готов», «ты сам»,
         «уверен», «решил». Если пол не указан — строй фразы так, чтобы не
         выдавать род («тебе стоит», «ты можешь»).
       - Если есть имя — можешь мягко обратиться по нему один раз (не в каждом
         предложении, без навязчивости).
    6. Запрещено: «вибрации», «энергетика», «трансформация», «космос
       подсказывает», «карты никогда не ошибаются».

    Формат ответа — СТРОГО по одному блоку на каждую позицию расклада,
    в порядке позиций, разделённые ПУСТОЙ СТРОКОЙ, затем финальный блок-итог.
    Каждый блок позиции — 2–4 предложения. Итог — 2–3 предложения с одним
    конкретным действием.

    Если расклад «на решение» (одна позиция «Ответ») — итог ОБЯЗАН начинаться
    со слова «Да» или «Нет» (можно «Да, но…» / «Нет, но…»).

    Не подписывай блоки заголовками и номерами — только текст блоков.
    Язык: только русский (кириллица). Без иероглифов и эмодзи.
    """,
).strip()


def _card_payload(card: TarotCard, position_label: str, position_meaning: str) -> dict:
    return {
        "позиция": position_label,
        "смысл_позиции": position_meaning,
        "карта": card.name_ru,
        "ключи": list(card.keywords),
        "астро_соответствие": card.astro_affinity,
        "голос_карты": card.voice,
    }


def build_spread_user_message(
    spec: SpreadSpec,
    question: str | None,
    cards: list[TarotCard],
    *,
    user_name: str | None = None,
    gender: str | None = None,
) -> str:
    """Расклад + вопрос: карты в порядке позиций спеки.

    user_name / gender — из профиля: род согласуется, имя используется мягко.
    """
    payload: dict = {}
    client: dict = {}
    if user_name:
        client["имя"] = user_name
    if gender:
        client["пол"] = gender
    if client:
        payload["клиент"] = client
    payload["расклад"] = spec.title_ru
    payload["вопрос"] = question or "вопрос не задан — прочитай расклад о текущем дне человека"
    payload["позиции"] = [
        _card_payload(card, position.label_ru, position.meaning)
        for position, card in zip(spec.positions, cards, strict=True)
    ]
    payload["число_блоков_в_ответе"] = spec.card_count + 1
    return (
        "Прочитай расклад как ответ на вопрос.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


_QUOTE_CHARS = {'"', "'", "«", "»"}
# Позиционный заголовок вида «Прошлое:» / «**Итог**:» отдельной строкой — снимаем,
# чтобы модель не «съедала» блок под подпись (мы сами подписываем позиции при выводе).
_LABEL_LINE = re.compile(r"^\s*[*_#>\s]*[А-ЯЁ][А-Яа-яёЁ ]{1,24}\s*[:：)]\s*$")


def clean_spread_output(raw: str) -> str:
    """Лёгкая очистка вывода модели БЕЗ переформатирования блоков.

    В отличие от sanitize_prediction_output (обработчик прогноза, схлопывает
    текст в «вопрос+прогноз+совет»), тут только снимаем обёртки — блочную
    структуру расклада сохраняем.
    """
    text = raw.strip()
    if not text:
        return ""
    # markdown-ограждения ```lang ... ```
    text = re.sub(r"^```\w*\n?", "", text)
    text = re.sub(r"\n?```$", "", text).strip()
    # кавычки вокруг всего ответа
    if len(text) >= 2 and text[0] in _QUOTE_CHARS and text[-1] in _QUOTE_CHARS:
        text = text[1:-1].strip()
    # схлопываем одиночные строки-заголовки позиций в следующий абзац
    lines = text.split("\n")
    merged: list[str] = []
    pending_label: str | None = None
    for line in lines:
        if _LABEL_LINE.match(line):
            pending_label = line.strip().rstrip(":：) ").strip("*_#> ")
            continue
        if pending_label and line.strip():
            merged.append(f"{pending_label}. {line.strip()}")
            pending_label = None
        else:
            merged.append(line)
    return "\n".join(merged).strip()


def normalize_spread_blocks(spec: SpreadSpec, text: str) -> str:
    """Лишние блоки сливаются в итог; недостающие не чиним — это retry."""
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    expected = spec.card_count + 1
    if len(blocks) <= expected:
        return "\n\n".join(blocks)
    head = blocks[: expected - 1]
    tail = " ".join(blocks[expected - 1 :])
    return "\n\n".join([*head, tail])


_MIN_POSITION_BLOCK_LEN = 40
_MIN_SUMMARY_LEN = 30


def validate_spread_output(spec: SpreadSpec, text: str) -> str | None:
    """None — валидно, иначе причина для retry."""
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    if len(blocks) != spec.card_count + 1:
        return "invalid_structure"
    *position_blocks, summary = blocks
    if any(len(block) < _MIN_POSITION_BLOCK_LEN for block in position_blocks):
        return "position_block_too_short"
    if len(summary) < _MIN_SUMMARY_LEN:
        return "summary_too_short"
    if spec.type is SpreadType.YES_NO:
        verdict = summary.lower().lstrip("«\"'— ")
        if not verdict.startswith(("да", "нет")):
            return "missing_verdict"
    return None
