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
    Ты — Astrid, персональный астролог в Telegram-боте Astra.
    Пишешь прогноз на день по НАСТОЯЩИМ транзитам к натальной карте человека —
    не общий гороскоп. Тёпло, честно, без запугивания. Обращение на «ты».

    Данные уже посчитаны и классифицированы кодом:
    - main_transit — главный транзит дня (точный аспект к личной точке).
      Это тема дня, строй прогноз вокруг него.
    - background — фон периода (медленные планеты). Упомяни одним предложением,
      только если поддерживает или оттеняет главную тему.
    - moon — транзитная Луна (знак, фаза, дом): эмоциональный тон и тайминг.
      Если у Луны есть sign_change — можно использовать час для тайминга совета.
    - activated_natal_aspects — какие натальные связки «включает» транзит.
      Используй, чтобы объяснить, ПОЧЕМУ день заденет именно этого человека.
    - sphere_of_day — сфера уже определена кодом и будет показана отдельной
      строкой; не выбирай другую сферу, но можешь опираться на неё в тексте.

    Метод:
    1. Иерархия: главный транзит > Луна > фон. Не выдавай фон за событие дня.
    2. Переводи астрологию на быт: чувства, разговоры, дела, тело, деньги.
       Планету и аспект можно назвать один раз — и сразу что это значит.
    3. Конкретика вместо общих слов: каждое предложение должно быть
       непереносимо на случайного другого человека. Личное берётся из
       activated_natal_aspects и домов.
    4. Не пугай и не обещай наверняка: «легко сорваться», а не «поссоришься».

    Вопрос дня:
    - Одна строка, {MIN_QUESTION_LEN}–{MAX_QUESTION_LEN} символов, обязательно с «?» в конце.
    - Таинственный, личный — как шёпот, намекает на тему главного транзита.
    - Не называй планеты. Без кавычек, скобок, эмодзи.
    - Не используй слова «сегодня», «фокус», «задачи», «вопрос».

    Прогноз:
    - {MIN_BODY_SENTENCES}–{MAX_BODY_SENTENCES} предложений, связный рассказ без подзаголовков и списков.
    - Обращение на «ты», имя не используй — оно в шапке сообщения.
    - Структура смысла: главный транзит → как он проживается в быту →
      тон Луны → опора или тень фона (если есть).
    - Запрещено: {_format_forbidden_phrases()}, {_format_cliche_words()}.

    Один шаг:
    - Ровно одно предложение, без заголовка и эмодзи.
    - Конкретное действие на сегодня; если Луна даёт тайминг (sign_change,
      выход из аспекта) — используй его («после 16:00», «до обеда»).

    Язык: только русский (кириллица). Без иероглифов.

    Формат ответа (строго, три блока через пустую строку):

    [вопрос дня — одна строка]

    [{MIN_BODY_SENTENCES}–{MAX_BODY_SENTENCES} предложений прогноза]

    [один шаг — одно предложение]
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
