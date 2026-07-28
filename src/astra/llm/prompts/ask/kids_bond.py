"""Продукт «Какими будут отношения с детьми?»: тип родителя и связь.

Тон здесь **категоричный** — это утверждённое отличие продукта. Персона раздела
запрещает фатализм всем остальным продуктам; тут переопределяем тон локально,
не трогая общий `base.PERSONA`, иначе категоричными станут все ответы разом.

Граница, которую держим: категоричны про родителя — его поведение, сильные
стороны, слепые зоны. Про самого ребёнка (судьба, здоровье, таланты, будущее)
не утверждаем ничего, и в схеме ответа для этого просто нет поля.
"""

from __future__ import annotations

import html
import json
from textwrap import dedent

from pydantic import BaseModel, Field

from astra.ask.kids_bond import KidsBondResult
from astra.llm.prompts.ask.base import find_banned_phrase, parse_json_into, too_short

MAX_TOKENS = 2000
TEMPERATURE = 0.7

ACTIONS_EXPECTED = 2
_MIN_SECTION = 110
_MIN_VIEW = 80
_MIN_ACTION = 25

# Слова-смягчители: их наличие означает, что модель ушла от категоричности.
HEDGING_WORDS: tuple[str, ...] = (
    "возможно",
    "может быть",
    "вероятно",
    "скорее всего",
    "наверное",
    "склонна",
    "склонен",
    "иногда",
    "порой",
    "как правило",
    "в целом",
    "часто",
)

# Про ребёнка ничего не предсказываем — страховка поверх схемы.
CHILD_PREDICTION_WORDS: tuple[str, ...] = (
    "ребёнок будет болеть",
    "у ребёнка будет талант",
    "судьба ребёнка",
    "ребёнок вырастет несчастн",
)


class KidsBondAnswer(BaseModel):
    archetype_line: str = Field(description="тип родителя одной фразой, как факт")
    why_in_chart: str = Field(description="2–3 фактора карты вслух и что каждый делает")
    strength: str = Field(description="что ребёнок получает от этого родителя лучше всего")
    tension: str = Field(description="где связь ломается: механизм, а не вина")
    inherited: str = Field(description="что человек повторяет за своими родителями")
    childs_view: str = Field(description="каким ребёнок видит его изнутри, словами ребёнка")
    when_it_starts: str | None = Field(
        default=None,
        description="только для бездетных: что включится в момент, когда ребёнок появится",
    )
    actions: list[str] = Field(description="ровно два проверяемых действия")


def expected_blocks(result: KidsBondResult) -> int:  # noqa: ARG001 — контракт раздела
    """У этого продукта переменная часть — только действия, их всегда два."""
    return ACTIONS_EXPECTED


def find_hedging(*texts: str) -> str | None:
    joined = " ".join(texts).lower()
    return next((word for word in HEDGING_WORDS if word in joined), None)


def validate(
    answer: KidsBondAnswer,
    expected_actions: int,
    result: KidsBondResult | None = None,
) -> str | None:
    """Причина retry или None. Смягчители — тоже причина: тон утверждён жёстким."""
    if len(answer.actions) != expected_actions:
        return "actions_count_mismatch"

    has_children = bool(result.has_children) if result is not None else True
    if not has_children:
        # Бездетному не выдаём инструкций про ребёнка, которого нет.
        if answer.when_it_starts is None or too_short(answer.when_it_starts, _MIN_SECTION):
            return "when_it_starts_missing"
        if any("ребёнк" in action.lower() or "ребенк" in action.lower() for action in answer.actions):
            return "action_about_missing_child"
    if any(too_short(action, _MIN_ACTION) for action in answer.actions):
        return "action_too_short"
    for field in (answer.why_in_chart, answer.strength, answer.tension, answer.inherited):
        if too_short(field, _MIN_SECTION):
            return "section_too_short"
    if too_short(answer.childs_view, _MIN_VIEW):
        return "childs_view_too_short"

    texts = (
        answer.archetype_line,
        answer.why_in_chart,
        answer.strength,
        answer.tension,
        answer.inherited,
        answer.childs_view,
        *answer.actions,
    )
    hedge = find_hedging(*texts)
    if hedge:
        return f"hedging:{hedge}"
    banned = find_banned_phrase(*texts)
    if banned:
        return f"banned_phrase:{banned}"
    joined = " ".join(texts).lower()
    if any(phrase in joined for phrase in CHILD_PREDICTION_WORDS):
        return "child_prediction_not_allowed"
    return None


def parse(raw: str) -> KidsBondAnswer | None:
    result = parse_json_into(KidsBondAnswer, raw)
    return result if isinstance(result, KidsBondAnswer) else None


SYSTEM_PROMPT = dedent(
    """\
    You are Астрид (Astrid), an astrologer inside the Telegram bot Astra. When
    naming yourself, write «Астрид» in Cyrillic only — never "Astrid" in Latin.

    CRITICAL LANGUAGE RULE: every JSON string VALUE must be written in RUSSIAN
    (Cyrillic) only. Never put Latin letters in values. JSON keys stay exactly
    as given, in English.

    Product: the answer to "What will my relationship with my children be like?"
    — a paid answer built on the person's natal chart.

    TONE — CATEGORICAL. This is the defining rule of this product. You state,
    you do not suppose. Write in the indicative: «Ты растишь ребёнка через дело,
    а не через слова», not «возможно, тебе будет проще…». Every sentence is a
    verdict about how this person parents.

    FORBIDDEN hedging words — the answer is rejected if any of them appear:
    «возможно», «может быть», «вероятно», «скорее всего», «наверное»,
    «склонна», «склонен», «иногда», «порой», «как правило», «в целом», «часто».
    No conditional mood («был бы», «могла бы»). No questions to the reader.
    This is checked automatically: one hedging word anywhere and the whole
    answer is thrown away. Whenever you are about to write «склонна» or
    «часто», write the behaviour itself instead: not «ты склонна опекать», but
    «ты опекаешь».

    WHAT YOU MAY NOT BE CATEGORICAL ABOUT — hard limit: never state anything
    about the child's fate, health, lifespan, talents, or future circumstances.
    Never predict conflict as inevitable damage. You describe the PARENT: their
    behaviour, their strengths, their blind spots, how the child perceives them.
    The child is never the object of a prediction.

    The archetype and all chart factors are ALREADY COMPUTED and given in the
    data. Never recompute them, never replace the archetype with another one,
    never add factors of your own. Your job is to make them land.

    How to write:
    - `archetype_line` — name the parent type in one sentence, as a fact. No digits.
    - `why_in_chart` — name 2–3 concrete factors from the data out loud
      («Луна в Скорпионе в 4 доме», «управитель 5 дома Юпитер в 11 доме») and say
      what each one does to this person's parenting. Never «звёзды говорят»,
      never «карта показывает».
    - `strength` — what the child receives from this parent better than from
      anyone else. A scene from life, not a quality.
    - `tension` — where it goes wrong. Say it straight, without softening and
      without blaming: it is a mechanism, not a fault.
    - `inherited` — what this person repeats after their own parents without
      noticing. Lean on the Moon and the 4th house. Only about upbringing, not
      about the family line at large.
    - `childs_view` — how the child sees this parent from the inside. Write it as
      the child's plain words, 2–3 sentences. This is the strongest part of the
      answer — make it precise.
    - `actions` — exactly two actions, each verifiable and doable this week.
      No «полюби себя», no «будь внимательнее».

    TWO BRANCHES, decided by `already_has_children` in the data:

    1) already_has_children = true — the child exists. `when_it_starts` must be
       null. `actions` are things to do WITH the child this week.

    2) already_has_children = false — there is no child yet. Then:
       - fill `when_it_starts`: what switches on in this person the moment a
         child appears. Name the first thing that will show up, and the exact
         situation where their type will surface. Categorical, 3–4 sentences.
       - `actions` are about the PERSON THEMSELVES, not about a child: their
         own parents, their boundaries, what they rehearse now and will bring
         into parenthood. The word «ребёнок» must not appear in the actions at
         all — the answer is rejected if it does. These are things to do this
         week without any child around.

    Barnum statements are forbidden — anything true for any parent («ты хочешь
    для ребёнка лучшего»). Every paragraph must be impossible to transfer to a
    random other person.
    Forbidden words: «вибрации», «энергетика», «трансформация», «космос
    подсказывает», «карма», «кармический», «задача души».
    Match grammatical gender to the person's gender from the data. If gender is
    unknown, phrase so gender is not revealed.
    Address the reader as «ты». No greetings, no goodbyes, no name in every field.

    Length: archetype_line 1 sentence, why_in_chart 3–4, strength 3–4,
    tension 3–4, inherited 3–4, childs_view 2–3, each action 1 sentence.

    Return ONLY valid JSON strictly per the schema. No markdown, no text around
    it, no comments.

    Response schema (JSON):
    {
      "archetype_line": "...",
      "why_in_chart": "...",
      "strength": "...",
      "tension": "...",
      "inherited": "...",
      "childs_view": "...",
      "actions": ["...", "..."]
    }
    """,
).strip()


def build_user_message(
    result: KidsBondResult,
    *,
    user_name: str | None = None,
    gender: str | None = None,
) -> str:
    payload = {
        "name": user_name or "unknown",
        "gender": gender or "unknown",
        "age": result.age,
        "already_has_children": result.has_children,
        "parent_archetype": result.archetype,
        "birth_time_known": result.factors.has_time,
        # Факторы — по-русски: они попадают в ответ как есть.
        "chart_factors": result.factors.notes,
        "moon_parenting_model": result.factors.moon_parenting_model,
        "mercury_talk_style": result.factors.mercury_talk_style,
    }
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        f"Computed data:\n{data}\n\n"
        "Remember: all string values in Russian. Categorical mood, no hedging "
        "words. Two actions, exactly."
    )


def card_caption(result: KidsBondResult) -> str:
    """Подпись под карточкой: тип родителя, без разбора."""
    return (
        f"Твой тип родителя — <b>{html.escape(result.archetype)}</b>: "
        f"{html.escape(result.tagline)}."
    )


def render_answer(answer: KidsBondAnswer, result: KidsBondResult) -> str:
    """HTML разбора: тип подставляет код, модель его не выбирает."""
    blocks = [
        f"🌱 <b>{html.escape(answer.archetype_line.strip())}</b>",
        "",
        html.escape(answer.why_in_chart.strip()),
        "",
        "💪 <b>Что ребёнок получит от тебя</b>",
        html.escape(answer.strength.strip()),
        "",
        "⚡️ <b>Где будет напряжение</b>",
        html.escape(answer.tension.strip()),
        "",
        "🧬 <b>Что ты повторяешь за своими родителями</b>",
        html.escape(answer.inherited.strip()),
        "",
        "👀 <b>Каким тебя видит ребёнок</b>",
        f"<i>{html.escape(answer.childs_view.strip())}</i>",
    ]

    if result.has_children:
        blocks.extend(
            [
                "",
                "✅ <b>Что делать</b>",
                *[f"• {html.escape(action.strip())}" for action in answer.actions],
            ],
        )
    else:
        # Ребёнка ещё нет: вместо инструкций «поиграй с ним» — момент включения
        # сценария и то, что можно сделать с собой уже сейчас.
        if answer.when_it_starts:
            blocks.extend(
                [
                    "",
                    "🔮 <b>Что включится, когда ребёнок появится</b>",
                    html.escape(answer.when_it_starts.strip()),
                ],
            )
        blocks.extend(
            [
                "",
                "✅ <b>Что сделать до этого</b>",
                *[f"• {html.escape(action.strip())}" for action in answer.actions],
            ],
        )
    if not result.factors.has_time:
        blocks.extend(
            [
                "",
                "<i>Время рождения неизвестно — считала по Луне и Меркурию, без домов. "
                "Впишешь время в профиле — пересчитаю точнее.</i>",
            ],
        )
    return "\n".join(blocks)
