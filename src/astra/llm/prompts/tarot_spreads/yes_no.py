"""Продукт «Расклад на решение» (Да/Нет): одна карта, прямой вердикт."""

from __future__ import annotations

from textwrap import dedent

from pydantic import BaseModel, Field

from astra.llm.prompts.tarot_spreads.base import (
    MIN_FIELD_LEN,
    PERSONA,
    TarotProduct,
    question_line,
    title_line,
)
from astra.tarot.card import TarotCard
from astra.tarot.spreads import SPREADS, SpreadType


class YesNoReading(BaseModel):
    verdict: str = Field(description="да | нет | да, но | нет, но")
    answer: str = Field(description="что карта говорит о вопросе как ответ")
    summary: str = Field(description="итог + одно конкретное действие")


_METHOD = dedent(
    """\
    Продукт: «Расклад на решение» (Да/Нет). Одна карта в позиции ответа.
    Дай ПРЯМОЙ ответ на вопрос и честно объясни его цену — без уклончивости.

    Схема JSON (верни ровно эти поля):
    {
      "verdict": "да / нет / да, но / нет, но — обязательно начинается со слова «да» или «нет»",
      "answer": "2–4 предложения: как карта в позиции ответа отвечает на вопрос",
      "summary": "1–2 предложения итога + одно конкретное действие на сегодня"
    }
    """,
)

SYSTEM_PROMPT = f"{PERSONA}\n\n{_METHOD}".strip()


class YesNoProduct(TarotProduct):
    spread_type = SpreadType.YES_NO
    spec = SPREADS[SpreadType.YES_NO]
    schema = YesNoReading
    system_prompt = SYSTEM_PROMPT
    max_tokens = 450

    def validate(self, data: YesNoReading) -> str | None:  # type: ignore[override]
        verdict = data.verdict.strip().lower().lstrip("«\"'— ")
        if not verdict.startswith(("да", "нет")):
            return "missing_verdict"
        if len(data.answer.strip()) < MIN_FIELD_LEN:
            return "answer_too_short"
        if len(data.summary.strip()) < 20:
            return "summary_too_short"
        return None

    def render(self, question: str | None, cards: list[TarotCard], data: YesNoReading) -> str:  # type: ignore[override]
        card = cards[0]
        verdict = data.verdict.strip().rstrip(".")
        verdict = verdict[:1].upper() + verdict[1:]
        lines = [title_line(self.spec)]
        q_line = question_line(question)
        if q_line:
            lines.append(q_line)
        lines += ["", f"{card.emoji} <b>{card.name_ru}</b>", data.answer.strip()]
        lines += ["", f"✨ <b>Итог — {verdict}:</b> {data.summary.strip()}"]
        return "\n".join(lines)
