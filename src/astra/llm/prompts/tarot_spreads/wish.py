"""Продукт «Загадай желание»: компактный ритуал на 3 карты.

Даёт честный вердикт «сбудется ли» + ориентировочный срок (дни/недели/месяцы/
сезон, не выдуманная дата). Позиции: Сердце желания → Что на пути → К чему идёт.
Тон — как в «Отношениях»: читаем именно те карты, что выпали, честно, без
прикрас и без фатализма.
"""

from __future__ import annotations

from textwrap import dedent

from pydantic import BaseModel, Field

from astra.llm.prompts.tarot_spreads.base import (
    PERSONA,
    TarotProduct,
    intro_position_lines,
    normalize_verdict,
    validate_field_lengths,
    verdict_summary_block,
)
from astra.tarot.card import TarotCard
from astra.tarot.spreads import SPREADS, SpreadType

_INTRO_MIN_LEN = 25
_TIMING_MIN_LEN = 15
# Вердикт обязан начинаться с узнаваемого слова — иначе retry (модель уклонилась).
_VERDICT_LEADS = ("сбуд", "пока", "вряд", "да", "нет", "не ")


class WishReading(BaseModel):
    verdict: str = Field(description="сбудется | сбудется, если | пока рано | вряд ли")
    timing: str = Field(description="честный срок: дни/недели/месяцы/сезон, без выдуманной даты")
    intro: str = Field(description="слова от Астрид: тёплое вступление 1–2 предложения")
    heart: str = Field(description="суть желания глазами карт")
    path: str = Field(description="что помогает и что мешает желанию")
    outcome: str = Field(description="к чему всё идёт при нынешнем раскладе")
    summary: str = Field(description="итог + одно конкретное действие")


def timing_block(timing: str) -> str:
    return f"⏳ <b>Когда сбудется:</b> {timing.strip()}"


# _METHOD — на английском (дешевле по токенам для DeepSeek). ВАЖНО: значения
# полей модель обязана писать по-русски. Правило честного срока изолировано здесь.
_METHOD = dedent(
    """\
    Product: the "Make a wish" spread — a compact ritual of 3 cards. The user
    made a wish; you tell them, by the cards, whether it will come true, WHEN
    (an honest timeframe), and what to do about it.

    CRITICAL LANGUAGE RULE: write every JSON string VALUE in RUSSIAN (Cyrillic)
    only. Never use Latin letters in values. Keep the JSON keys exactly as given
    below (in English).

    READ THE CARDS AS THEY FELL — honesty over comfort:
    - Read the exact card in each position, including hard ones. Do NOT sugar-coat
      and do NOT turn a difficult card into a pleasant one. Warmth is in the TONE
      (gentle, "ты"), never in distorting the card's meaning.
    - This is NOT fatalism: if the wish is unlikely, say it honestly ("пока не
      складывается", "вряд ли в этом виде") and show what could change it —
      never a life-sentence, never fake hope.
    - Match the client's grammatical gender from field "пол".

    VERDICT (field "verdict"): one honest short phrase that MUST start with one of:
    «Сбудется», «Сбудется, если …», «Пока рано», «Вряд ли». Choose by the cards,
    not by what is pleasant.

    TIMING (field "timing"): an HONEST timeframe in real units — days, weeks,
    months or a season (e.g. «ориентировочно 2–3 месяца», «в пределах полугода»,
    «несколько недель»). NEVER invent an exact date. Derive it from the energy of
    the spread (mostly the outcome card). If the wish does not come true at the
    current balance, say the timeframe does not read yet («срок пока не читается»).

    FIXED STRUCTURE. Return JSON with EXACTLY these seven fields:

    1) verdict — see above.
    2) timing — see above.
    3) intro (Astrid's words). 1-2 warm sentences that open the ritual and signal
       an honest answer, including the timeframe. No name, no greeting beyond this.
    4) heart (Сердце желания). The essence of the wish through the first card —
       what the person truly wants underneath.
    5) path (Что на пути). The second card: what helps and what blocks the wish
       right now, honestly.
    6) outcome (К чему идёт). The third card: where it heads at the current balance
       of forces — this card mainly drives verdict and timing.
    7) summary (Итог). Tie it together and give ONE concrete action. Honest,
       no fake comfort.

    Rules: intro is the only opening; heart/path/outcome contain ONLY the meaning
    of their own card — no greetings, no name. The cards echo each other.

    JSON schema (return exactly these fields; VALUES IN RUSSIAN):
    {
      "verdict": "Сбудется / Сбудется, если … / Пока рано / Вряд ли",
      "timing": "honest timeframe in days/weeks/months/season",
      "intro": "1-2 sentences: warm opening from Astrid",
      "heart": "2-3 sentences: the essence of the wish",
      "path": "2-3 sentences: what helps and what blocks it",
      "outcome": "2-3 sentences: where it heads now",
      "summary": "1-2 sentences of conclusion + one concrete action"
    }

    How the user sees the final message (structure is fixed; the emoji and card
    names are added by us — do NOT write them yourself):
    🌟 Загадай желание
    [intro]
    💫 Сердце желания — <card>: [heart]
    🛤 Что на пути — <card>: [path]
    🌙 К чему идёт — <card>: [outcome]
    ⏳ Когда сбудется: [timing]
    ✨ Вердикт — [verdict]: [summary]
    """,
)

SYSTEM_PROMPT = f"{PERSONA}\n\n{_METHOD}".strip()


class WishProduct(TarotProduct):
    spread_type = SpreadType.WISH
    spec = SPREADS[SpreadType.WISH]
    schema = WishReading
    system_prompt = SYSTEM_PROMPT
    max_tokens = 700

    def validate(self, data: WishReading) -> str | None:  # type: ignore[override]
        if not normalize_verdict(data.verdict).startswith(_VERDICT_LEADS):
            return "missing_verdict"
        if len(data.intro.strip()) < _INTRO_MIN_LEN:
            return "field_intro_too_short"
        if len(data.timing.strip()) < _TIMING_MIN_LEN:
            return "field_timing_too_short"
        return validate_field_lengths(data, ["heart", "path", "outcome"])

    def render(self, question: str | None, cards: list[TarotCard], data: WishReading) -> str:  # type: ignore[override]
        # Заголовок → слова от Астрид → 3 карты → срок → вердикт с итогом.
        lines = intro_position_lines(self.spec, question, cards, data)
        lines += ["", timing_block(data.timing)]
        lines += ["", verdict_summary_block(data.verdict, data.summary, label="Вердикт")]
        return "\n".join(lines)
