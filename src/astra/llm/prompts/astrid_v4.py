"""Astrid v4: прогноз дня по классифицированным транзитам к полной карте.

Ключевое отличие от v3: астрология уже посчитана и взвешена кодом
(главный транзит / фон / Луна / активированные натальные аспекты / сфера дня) —
LLM переводит её на язык быта. Формат вывода тот же: 3 текстовых блока,
шапку и сферу дня подставляет код при сборке сообщения.
"""

from __future__ import annotations

import json
from textwrap import dedent

from astra.astro.daily_context import DailyContextV2
from astra.llm.prompts.astrid import (
    MAX_BODY_SENTENCES,
    MAX_QUESTION_LEN,
    MIN_BODY_SENTENCES,
    MIN_QUESTION_LEN,
    QUESTION_ARCHETYPES,
    QuestionArchetype,
    _format_cliche_words,
    _format_forbidden_phrases,
    format_archetype_hint,
)

SYSTEM_PROMPT_V4 = dedent(
    f"""
    Ты — Астрид, персональный астролог в Telegram-боте Astra. Если называешь
    себя — только «Астрид» (кириллицей), никогда «Astrid».
    Пишешь прогноз на день по НАСТОЯЩИМ транзитам к натальной карте человека —
    не общий гороскоп. Тёпло, честно, без запугивания. Обращение на «ты».

    Данные уже посчитаны и классифицированы кодом:
    - main_transit — главный транзит дня (точный аспект к личной точке).
      Это тема дня, строй прогноз вокруг него.
    - conflict — ГЛАВНОЕ: два реально противоречащих слоя неба (side_a и side_b).
      Прогноз строится как их спор; не разрешай его — оставь развилку открытой.
    - background — фон периода (медленные планеты). Одним предложением,
      только если оттеняет спор.
    - moon — транзитная Луна (знак, фаза, дом): эмоциональный тон и тайминг.
    - activated_natal_aspects — какие натальные связки «включает» транзит.
      Используй, чтобы объяснить, ПОЧЕМУ этот спор заденет именно этого человека.

    Метод:
    1. Драматургия: покажи обе стороны конфликта в быту — где сила side_a
       откроет дверь и где она же захлопнет другую (side_b).
    2. Переводи астрологию на быт: чувства, разговоры, дела, тело, деньги.
       Планету и аспект можно назвать один раз — и сразу что это значит.
    3. Конкретика вместо общих слов: каждое предложение должно быть
       непереносимо на случайного другого человека.
    4. Не пугай и не обещай наверняка: «легко сорваться», а не «поссоришься».
    5. НЕ давай совета и не подсказывай решение — прогноз заканчивается
       открытой развилкой. Ответ человек получит у карт.

    Вопрос дня:
    - Одна строка, {MIN_QUESTION_LEN}–{MAX_QUESTION_LEN} символов, обязательно с «?» в конце.
    - Таинственный, личный — как шёпот, намекает на конфликт дня.
    - Не называй планеты. Без кавычек, скобок, эмодзи.
    - Не используй слова «сегодня», «фокус», «задачи», «вопрос».

    Прогноз:
    - {MIN_BODY_SENTENCES}–{MAX_BODY_SENTENCES} предложений, связный рассказ без подзаголовков и списков.
    - Обращение на «ты», имя не используй — оно в шапке сообщения.
    - Структура: сила дня (side_a) → где она обернётся против (side_b) →
      чем этот выбор дорог именно этому человеку.
    - Без советов, рекомендаций и «лучше сделай так».
    - Запрещено: {_format_forbidden_phrases()}, {_format_cliche_words()}.

    Строка конфликта:
    - Ровно одно предложение-развилка формата «сделать A — или сохранить B».
    - Обязательно слово «или». Без планет, без вопросительного знака.
    - Обе стороны — из жизни, не из астрологии: «настоять на своём — или
      сберечь то, что между вами».

    Язык: только русский (кириллица). Без иероглифов.

    Формат ответа (строго, три блока через пустую строку):

    [вопрос дня — одна строка]

    [{MIN_BODY_SENTENCES}–{MAX_BODY_SENTENCES} предложений прогноза]

    [строка конфликта — одно предложение с «или»]
    """,
).strip()


def _sign_prep(sign: str) -> str:
    from astra.astro.constants import SIGN_RU_PREPOSITIONAL

    return SIGN_RU_PREPOSITIONAL.get(sign, sign)


def _transit_payload(t) -> dict:  # noqa: ANN001
    payload: dict = {
        "транзит": t.transit_planet,
        "аспект": t.aspect,
        "к_натальной": f"{t.natal_point} в {_sign_prep(t.natal_sign)}",
        "орб": t.orb_deg,
    }
    if t.natal_house is not None:
        payload["натальный_дом"] = t.natal_house
    return payload


def build_context_payload(ctx: DailyContextV2) -> dict:
    """JSON-представление контекста для user message."""
    payload: dict = {
        "дата": ctx.date.isoformat(),
        "натал": ctx.big_three,
        "main_transit": _transit_payload(ctx.main_transit) if ctx.main_transit else None,
        "background": [_transit_payload(t) for t in ctx.background],
    }
    if ctx.moon is not None:
        moon: dict = {
            "знак": ctx.moon.sign,
            "фаза": ctx.moon.phase,
        }
        if ctx.moon.natal_house is not None:
            moon["натальный_дом"] = ctx.moon.natal_house
        if ctx.moon.aspects:
            moon["аспекты"] = [_transit_payload(t) for t in ctx.moon.aspects]
        if ctx.moon.sign_change is not None:
            moon["смена_знака"] = {
                "в_знак": ctx.moon.sign_change.to_sign,
                "около_часа": ctx.moon.sign_change.approx_hour,
            }
        payload["moon"] = moon
    if ctx.activated_natal_aspects:
        payload["activated_natal_aspects"] = [
            {
                "связка": f"{a.p1} {a.aspect} {a.p2}",
                "включает": a.triggered_by,
            }
            for a in ctx.activated_natal_aspects
        ]
    if ctx.conflict is not None:
        payload["conflict"] = {
            "side_a": ctx.conflict.side_a,
            "side_b": ctx.conflict.side_b,
        }
    if ctx.sphere_of_day is not None:
        payload["sphere_of_day"] = ctx.sphere_of_day.label
    if not ctx.has_time:
        payload["примечание"] = (
            "время рождения неизвестно: дома и асцендент не рассчитаны, "
            "не упоминай их"
        )
    return payload


def resolve_archetype(archetype_id: str | None) -> QuestionArchetype | None:
    if archetype_id is None:
        return None
    return next((a for a in QUESTION_ARCHETYPES if a.id == archetype_id), None)


def build_user_message_v4(
    ctx: DailyContextV2,
    *,
    archetype: QuestionArchetype | None = None,
) -> str:
    archetype = archetype or resolve_archetype(ctx.question_archetype_id)
    hint = format_archetype_hint(archetype) if archetype is not None else ""
    context_json = json.dumps(build_context_payload(ctx), ensure_ascii=False, indent=2)
    parts = [
        "Составь прогноз на день по этому контексту.",
        "",
        context_json,
    ]
    if hint:
        parts += ["", hint]
    return "\n".join(parts)
