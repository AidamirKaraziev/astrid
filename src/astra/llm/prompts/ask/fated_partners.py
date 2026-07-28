"""Продукт «Сколько судьбоносных партнёров?»: разбор поверх готовых чисел.

Числа (сколько всего, сколько уже было, сколько впереди) и окна времени
считает `astra.ask.fated_partners`. Модель получает их вместе с факторами
карты и пишет живой разбор: портрет каждого партнёра, по каким признакам его
узнать, когда он приходит и что человек делает не так.

Схема ответа намеренно без чисел: посчитанное подставляет код.
"""

from __future__ import annotations

import html
import json
from textwrap import dedent

from pydantic import BaseModel, Field

from astra.ask.schemas import FatedPartnersResult, PartnershipWindow
from astra.llm.prompts.ask.base import PERSONA, find_banned_phrase, parse_json_into, too_short

MAX_TOKENS = 2600
TEMPERATURE = 0.75

_MIN_PORTRAIT = 120
_MIN_SECTION = 100
_MIN_MARKERS = 2

_MONTHS_RU = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


class PartnerSketch(BaseModel):
    """Портрет одного судьбоносного партнёра."""

    stage: str = Field(description="кто это по счёту и в каком периоде жизни: 3–6 слов")
    portrait: str = Field(description="каким он будет/был: характер, поведение, чем цепляет")
    brings: str = Field(description="что этот союз приносит в жизнь")
    teaches: str = Field(description="чему учит и чем заканчивается, если заканчивается")
    markers: list[str] = Field(description="2–3 конкретных признака, по которым его узнать")


class FatedPartnersAnswer(BaseModel):
    opening: str = Field(description="1–2 фразы захода, без приветствия")
    verdict: str = Field(description="как назвать расклад словами, без цифр")
    partners: list[PartnerSketch]
    already_lived: str = Field(description="что из этого уже прожито и как это выглядело")
    what_you_miss: str = Field(description="что человек делает не так и как из-за этого теряет")
    closing: str = Field(description="итог + одно конкретное действие")


def validate(answer: FatedPartnersAnswer, expected_partners: int) -> str | None:
    """Причина retry или None, если ответ годится."""
    if len(answer.partners) != expected_partners:
        return "partners_count_mismatch"
    for partner in answer.partners:
        if too_short(partner.portrait, _MIN_PORTRAIT):
            return "portrait_too_short"
        if len(partner.markers) < _MIN_MARKERS:
            return "markers_too_few"
    if too_short(answer.already_lived, _MIN_SECTION) or too_short(
        answer.what_you_miss,
        _MIN_SECTION,
    ):
        return "section_too_short"
    banned = find_banned_phrase(
        answer.opening,
        answer.verdict,
        answer.already_lived,
        answer.what_you_miss,
        answer.closing,
        *(p.portrait for p in answer.partners),
    )
    return f"banned_phrase:{banned}" if banned else None


def parse(raw: str) -> FatedPartnersAnswer | None:
    result = parse_json_into(FatedPartnersAnswer, raw)
    return result if isinstance(result, FatedPartnersAnswer) else None


_METHOD = dedent(
    """\
    Product: the answer to "How many fated partners will I have?" in a Telegram
    astrology bot. A fated partner = a turning-point union after which the person
    is different. Marriage is NOT required.

    CRITICAL: all numbers are ALREADY COMPUTED from the natal chart and given to
    you in the data. Never recompute, never contradict, never invent extra ones.
    Your job is to explain where they come from and what these people are like.

    CRITICAL LANGUAGE RULE: write every JSON string VALUE in RUSSIAN (Cyrillic)
    only. Keep the JSON keys exactly as given, in English.

    How to build the answer:
    - `partners` — exactly one entry per fated partner, in chronological order.
      The ones already lived come first (the data says how many), then the ones
      ahead. In `stage` say plainly which one this is and in what period of life.
    - For partners ahead, lean on the timing windows in the data (transit and
      age). Say the period the way a person speaks: "ближе к 34–35", "в
      ближайшие два года" — never a fabricated exact date.
    - `markers` — concrete recognisable signs (how they appear, how they behave,
      where the meeting happens), not virtues like "надёжный" or "добрый".
    - `already_lived` — connect the past windows to what the person likely went
      through; be careful and non-accusatory, this is their real life.
    - `what_you_miss` — the honest part: the pattern from the chart factors that
      makes them lose or not notice these people.

    Length: portrait 3–5 sentences, brings/teaches 2–3 sentences each,
    already_lived and what_you_miss 3–5 sentences, closing 2–3 sentences.
    """,
).strip()

SYSTEM_PROMPT = f"{PERSONA}\n\n{_METHOD}"


def _window_line(window: PartnershipWindow) -> str:
    return (
        f"{window.transit} к точке «{window.target}», пик "
        f"{_MONTHS_RU[window.peak.month - 1]} {window.peak.year}, возраст {window.age}"
    )


def build_user_message(
    result: FatedPartnersResult,
    *,
    user_name: str | None = None,
    gender: str | None = None,
) -> str:
    """Данные для модели: посчитанные числа + факторы карты + окна времени."""
    payload = {
        "имя": user_name or "не указано",
        "пол": gender or "не указан",
        "возраст": result.age,
        "сейчас_в_отношениях": "да" if result.in_relationship else "нет",
        "судьбоносных_всего": result.total,
        "уже_было": result.past,
        "впереди": result.future,
        "время_рождения_известно": "да" if result.factors.has_time else "нет",
        "факторы_карты": result.factors.notes,
        "окна_в_прошлом": [_window_line(w) for w in result.windows_past],
        "окна_впереди": [_window_line(w) for w in result.windows_future],
    }
    schema_hint = dedent(
        """\
        Схема ответа (JSON):
        {
          "opening": "...",
          "verdict": "...",
          "partners": [
            {"stage": "...", "portrait": "...", "brings": "...", "teaches": "...",
             "markers": ["...", "..."]}
          ],
          "already_lived": "...",
          "what_you_miss": "...",
          "closing": "..."
        }
        """,
    ).strip()
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        f"Данные расчёта:\n{data}\n\n"
        f"В массиве partners ровно {result.total} элементов: "
        f"сначала {result.past} уже прожитых, затем {result.future} впереди.\n\n"
        f"{schema_hint}"
    )


def _plural_partners(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "судьбоносный партнёр"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return "судьбоносных партнёра"
    return "судьбоносных партнёров"


def card_caption(result: FatedPartnersResult) -> str:
    """Подпись под карточкой: числа словами, без разбора."""
    total = result.total
    parts = [f"<b>{total} {_plural_partners(total)}</b> — столько показывает твоя карта."]
    if result.past and result.future:
        parts.append(f"Уже было: <b>{result.past}</b>. Впереди: <b>{result.future}</b>.")
    elif result.past:
        parts.append(f"И все <b>{result.past}</b> уже случились — разбираю ниже, кто это был.")
    else:
        parts.append(f"Все <b>{result.future}</b> — впереди.")
    return "\n".join(parts)


def render_answer(answer: FatedPartnersAnswer, result: FatedPartnersResult) -> str:
    """HTML разбора для Telegram: числа подставляет код, не модель."""
    blocks: list[str] = [
        html.escape(answer.opening.strip()),
        "",
        f"✨ <b>{html.escape(answer.verdict.strip())}</b>",
    ]
    for index, partner in enumerate(answer.partners, start=1):
        blocks.extend(
            [
                "",
                f"<b>{index}. {html.escape(partner.stage.strip())}</b>",
                html.escape(partner.portrait.strip()),
                f"<i>Что приносит:</i> {html.escape(partner.brings.strip())}",
                f"<i>Чему учит:</i> {html.escape(partner.teaches.strip())}",
                "<i>Как узнать:</i>",
                *[f"• {html.escape(marker.strip())}" for marker in partner.markers],
            ],
        )
    blocks.extend(
        [
            "",
            "🕰 <b>Что уже прожито</b>",
            html.escape(answer.already_lived.strip()),
            "",
            "⚠️ <b>Где ты их теряешь</b>",
            html.escape(answer.what_you_miss.strip()),
            "",
            html.escape(answer.closing.strip()),
        ],
    )
    if not result.factors.has_time:
        blocks.extend(
            [
                "",
                "<i>Время рождения неизвестно — считала по Венере и её аспектам, "
                "без домов. Впишешь время в профиле — пересчитаю точнее.</i>",
            ],
        )
    return "\n".join(blocks)
