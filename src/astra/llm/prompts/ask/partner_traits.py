"""Продукт «Черты моего судьбоносного партнёра?»: портрет поверх типажа.

Типаж, возраст, среду, темп речи и манеру держаться считает
`astra.ask.partner_traits`. Модель получает всё это готовым и пишет живой
портрет — она типаж не выбирает и не переименовывает.

Два правила, которых нет у соседних продуктов:

- **Имени модель не видит.** Обращение вставляет код при рендере
  (`ask/naming.py`), поэтому имя звучит ровно дважды и не может «посыпаться».
  Заход и финал модель пишет как продолжение обращения — со строчной буквы.
- **Род партнёра решает код** по полу из профиля и передаёт одним словом:
  карта пол партнёра не показывает, гадать об этом модели нечего.

Граница продукта: только «кто он». Места встречи и сроки принадлежат вопросу
«Где меня ждёт судьбоносная встреча?» — здесь они прямо запрещены.
"""

from __future__ import annotations

import html
import json
from textwrap import dedent

from pydantic import BaseModel, Field

from astra.ask.partner_traits import PartnerTraitsResult
from astra.llm.prompts.ask.base import PERSONA, find_banned_phrase, parse_json_into, too_short
from astra.users.gender import GENDER_FEMALE, GENDER_MALE

MAX_TOKENS = 2200
TEMPERATURE = 0.75

_TRAITS_EXPECTED = 3
_MIN_RECOGNISE = 3
_MAX_RECOGNISE = 4
_MIN_PORTRAIT = 150
_MIN_SECTION = 100
_MIN_TRAIT = 80

# Род партнёра: карта его не показывает, поэтому берём от обратного к полу
# человека. Пол не задан — пишем нейтрально, ничего не додумывая.
_PARTNER_GENDER: dict[str, str] = {
    GENDER_FEMALE: "мужской",
    GENDER_MALE: "женский",
}
_PARTNER_GENDER_NEUTRAL = "нейтральный"


class TraitBlock(BaseModel):
    """Одна черта характера партнёра, привязанная к фактору карты."""

    title: str = Field(description="черта в 2–4 словах, без точки")
    text: str = Field(description="как это выглядит в жизни + фактор карты, из которого следует")


class PartnerTraitsAnswer(BaseModel):
    opening: str = Field(
        description="1–2 фразы захода. Это продолжение обращения к человеку: начинай со строчной буквы",
    )
    portrait: str = Field(description="кто этот человек: типаж живыми словами, сцена из жизни")
    traits: list[TraitBlock]
    recognise: list[str] = Field(description="3–4 признака, по которым его узнать при встрече")
    glue: str = Field(description="что вас склеит и почему вам будет хорошо вместе")
    friction: str = Field(description="где между вами будет напряжение и на чём оно ломается")
    closing: str = Field(
        description="итог + одно конкретное действие. Продолжение обращения: начинай со строчной",
    )


def expected_blocks(result: PartnerTraitsResult) -> int:  # noqa: ARG001 — контракт раздела
    """Черт характера всегда три: портрет из трёх опор читается, из семи — нет."""
    return _TRAITS_EXPECTED


def validate(
    answer: PartnerTraitsAnswer,
    expected_traits: int,
    result: PartnerTraitsResult | None = None,  # noqa: ARG001 — контракт раздела
) -> str | None:
    """Причина retry или None, если ответ годится."""
    if len(answer.traits) != expected_traits:
        return "traits_count_mismatch"
    for trait in answer.traits:
        if too_short(trait.text, _MIN_TRAIT):
            return "trait_too_short"
    if not _MIN_RECOGNISE <= len(answer.recognise) <= _MAX_RECOGNISE:
        return "recognise_count"
    if too_short(answer.portrait, _MIN_PORTRAIT):
        return "portrait_too_short"
    if too_short(answer.glue, _MIN_SECTION) or too_short(answer.friction, _MIN_SECTION):
        return "section_too_short"
    banned = find_banned_phrase(
        answer.opening,
        answer.portrait,
        answer.glue,
        answer.friction,
        answer.closing,
        *(t.text for t in answer.traits),
        *answer.recognise,
    )
    return f"banned_phrase:{banned}" if banned else None


def parse(raw: str) -> PartnerTraitsAnswer | None:
    result = parse_json_into(PartnerTraitsAnswer, raw)
    return result if isinstance(result, PartnerTraitsAnswer) else None


_METHOD = dedent(
    """\
    Product: the answer to "What is my fated partner like?" in a Telegram
    astrology bot. A fated partner = a turning-point union after which the
    person is different. Marriage is NOT required, and nothing is guaranteed:
    the chart shows a type, not a verdict.

    CRITICAL: the partner type, their likely age, the circle they come from,
    how they speak and how they carry themselves are ALREADY COMPUTED from the
    natal chart and given to you in the data. Never replace the type, never
    rename it, never offer a second one. Your job is to make it a living person.

    CRITICAL LANGUAGE RULE: write every JSON string VALUE in RUSSIAN (Cyrillic)
    only. Keep the JSON keys exactly as given, in English.

    WHOSE CHART THIS IS: the data describes the READER's natal chart, never the
    partner's. Houses, planets and aspects belong to the reader: write «твой
    седьмой дом», «управитель твоего 7 дома», «Венера в твоей карте». Never
    write «её 7 дом» or «его Юпитер» — the partner's own chart is unknown here.

    GRAMMATICAL GENDER OF THE PARTNER: field "partner_gender" in the data.
    "мужской" — write about the partner as «он». "женский" — as «она».
    "нейтральный" — never reveal a gender: use «этот человек», «твой человек»
    and phrasings that work for anyone. This is data, not your guess.

    NEVER address the person by name and never invent one — the interface adds
    the address itself. "opening" and "closing" are continuations of that
    address, so those two — and ONLY those two — start with a lowercase letter.
    Every other field is ordinary text and starts with a capital letter.

    BOUNDARY — where they will be met is NOT this product's answer. Never name
    a place, a city, an app, an event or a date of meeting, and never say "soon"
    or "this year". The circle they come from is given in "origin" — you may
    lean on it to describe the person, never as a route to find them.

    How to build the answer:
    - `portrait` — one scene, not a list of virtues: how this person walks into
      a room, what they do first, why the reader would notice them.
    - `traits` — exactly three. Each one leans on a named chart factor from the
      data («управитель 7 дома — Сатурн в Козероге»), spoken out loud inside
      the text. Not "надёжный" but what that looks like on a Tuesday evening.
    - `recognise` — 3–4 signs you could check against a real living person:
      how they behave on a first meeting, what they say, what they do with
      their hands, what they never do. No virtues, no horoscope words.
    - `glue` and `friction` — honest and specific, built on the aspects in the
      data. `friction` must not read as a warning to run away.
    - If "in_relationship_now" is true, `closing` invites them to check the
      person next to them against this portrait — WITHOUT ever ruling whether
      it is them or not. If false, `closing` is about not walking past.

    Length: portrait 4–6 sentences, each trait 2–3 sentences, glue and friction
    3–4 sentences each, closing 2–3 sentences.
    """,
).strip()

SYSTEM_PROMPT = f"{PERSONA}\n\n{_METHOD}"


def _partner_gender(gender: str | None) -> str:
    return _PARTNER_GENDER.get(gender or "", _PARTNER_GENDER_NEUTRAL)


def build_user_message(
    result: PartnerTraitsResult,
    *,
    user_name: str | None = None,  # noqa: ARG001 — имя подставляет код, модель его не видит
    gender: str | None = None,
) -> str:
    """Данные для модели: посчитанный типаж + факторы карты + род партнёра."""
    payload = {
        # Пол самого человека: по нему PERSONA согласует род во всём тексте.
        "gender": gender or "unknown",
        "partner_gender": _partner_gender(gender),
        "your_age": result.age,
        "in_relationship_now": result.in_relationship,
        "partner_type": result.archetype,
        "partner_type_means": result.tagline,
        "second_shade": result.shade,
        "age_hint": result.age_hint,
        "origin": result.origin,
        "how_they_speak": result.pace,
        "how_they_carry_themselves": result.bearing,
        "birth_time_known": result.factors.has_time,
        # Факторы по-русски: они попадают в ответ как есть.
        "chart_factors": result.factors.notes,
    }
    schema_hint = dedent(
        """\
        Response schema (JSON):
        {
          "opening": "...",
          "portrait": "...",
          "traits": [{"title": "...", "text": "..."}],
          "recognise": ["...", "...", "..."],
          "glue": "...",
          "friction": "...",
          "closing": "..."
        }
        """,
    ).strip()
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        f"Computed data:\n{data}\n\n"
        f"The traits array holds exactly {_TRAITS_EXPECTED} items.\n"
        f"The partner type is «{result.archetype}» and it cannot be changed.\n"
        f"Remember: all string values in Russian, opening and closing start lowercase.\n\n"
        f"{schema_hint}"
    )


def card_caption(result: PartnerTraitsResult) -> str:
    """Подпись под карточкой: типаж и его смысл, без разбора."""
    parts = [f"<b>{html.escape(result.archetype)}</b> — {html.escape(result.tagline)}."]
    parts.append("Такой типаж партнёра показывает твоя карта.")
    return "\n".join(parts)


def render_answer(
    answer: PartnerTraitsAnswer,
    result: PartnerTraitsResult,
    *,
    user_name: str | None = None,
) -> str:
    """HTML разбора для Telegram. Имя и посчитанные штрихи подставляет код."""
    from astra.ask.naming import address, sentence

    blocks: list[str] = [
        html.escape(address(answer.opening, user_name)),
        "",
        f"✨ <b>{html.escape(result.archetype)}</b> — {html.escape(result.tagline)}",
        "",
        html.escape(sentence(answer.portrait)),
    ]
    for trait in answer.traits:
        blocks.extend(
            [
                "",
                f"<b>{html.escape(sentence(trait.title))}</b>",
                html.escape(sentence(trait.text)),
            ],
        )

    # Посчитанное идёт отдельным блоком с подписями: так видно, где факты из
    # карты, а где наблюдения. Вперемешку с маркерами модели это читалось кашей.
    blocks.append("")
    blocks.append("📌 <b>Коротко</b>")
    blocks.extend(
        f"<i>{html.escape(label)}:</i> {html.escape(value)}"
        for label, value in _computed_markers(result)
    )

    blocks.extend(["", "🔎 <b>Как узнать при встрече</b>"])
    blocks.extend(f"• {html.escape(sentence(marker))}" for marker in answer.recognise)

    blocks.extend(
        [
            "",
            "💞 <b>Что вас склеит</b>",
            html.escape(sentence(answer.glue)),
            "",
            "⚠️ <b>Где будет трудно</b>",
            html.escape(sentence(answer.friction)),
            "",
            html.escape(address(answer.closing, user_name)),
        ],
    )
    if not result.factors.has_time:
        blocks.extend(
            [
                "",
                "<i>Время рождения неизвестно — считала по Венере и её аспектам, "
                "без домов. Впишешь время в профиле — портрет станет точнее.</i>",
            ],
        )
    return "\n".join(blocks)


def _computed_markers(result: PartnerTraitsResult) -> list[tuple[str, str]]:
    """Штрихи, которые посчитал Python: возраст, среда, речь, манера."""
    markers = [("Возраст", result.age_hint)]
    if result.origin:
        markers.append(("Среда", result.origin))
    if result.pace:
        markers.append(("Речь", result.pace))
    if result.bearing:
        markers.append(("Манера", result.bearing))
    return markers
