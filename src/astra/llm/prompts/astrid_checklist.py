"""Программный чеклист качества Astrid v3 (E2E)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from astra.llm.prompts.astrid import (
    MAX_BODY_SENTENCES,
    MAX_BODY_WORDS,
    MAX_QUESTION_LEN,
    MIN_BODY_SENTENCES,
    MIN_BODY_WORDS,
    MIN_QUESTION_LEN,
    validate_prediction_output,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")
_WORD_SPLIT = re.compile(r"\w+", flags=re.UNICODE)


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def split_v3_blocks(text: str) -> tuple[str, str, str] | None:
    parts = [part.strip() for part in text.strip().split("\n\n") if part.strip()]
    if len(parts) < 3:
        return None
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    return parts[0], parts[1], " ".join(parts[2:])


def run_v3_checklist(text: str, display_name: str) -> list[CheckResult]:
    """Проверки формата v3 для E2E/smoke."""
    results: list[CheckResult] = []

    validation_error = validate_prediction_output(text, display_name)
    results.append(
        CheckResult(
            "validate_prediction_output",
            validation_error is None,
            validation_error or "ok",
        ),
    )

    blocks = split_v3_blocks(text)
    results.append(
        CheckResult(
            "three_blocks",
            blocks is not None,
            "3 блока через пустую строку" if blocks else "неверная структура",
        ),
    )
    if blocks is None:
        return results

    question, body, advice = blocks

    results.append(
        CheckResult(
            "no_legacy_emoji",
            not any(marker in text for marker in ("✨", "💡", "🔢", "🎨")),
            "без v2-секций",
        ),
    )
    results.append(
        CheckResult(
            "question_push_length",
            MIN_QUESTION_LEN <= len(question) <= MAX_QUESTION_LEN,
            f"{len(question)} симв. (лимит {MIN_QUESTION_LEN}–{MAX_QUESTION_LEN})",
        ),
    )
    results.append(
        CheckResult(
            "question_ends_with_qmark",
            question.endswith("?"),
            question[-1:] or "пусто",
        ),
    )

    body_sentences = [s for s in _SENTENCE_SPLIT.split(body) if s.strip()]
    results.append(
        CheckResult(
            "body_sentence_count",
            MIN_BODY_SENTENCES - 1 <= len(body_sentences) <= MAX_BODY_SENTENCES + 1,
            f"{len(body_sentences)} предл. (целевой {MIN_BODY_SENTENCES}–{MAX_BODY_SENTENCES})",
        ),
    )

    body_words = len(_WORD_SPLIT.findall(body))
    results.append(
        CheckResult(
            "body_word_count",
            MIN_BODY_WORDS <= body_words <= MAX_BODY_WORDS,
            f"{body_words} слов (лимит {MIN_BODY_WORDS}–{MAX_BODY_WORDS})",
        ),
    )

    first_sentence = body_sentences[0] if body_sentences else ""
    results.append(
        CheckResult(
            "name_in_first_sentence",
            first_sentence.startswith(f"{display_name},")
            or first_sentence.startswith(f"{display_name} "),
            first_sentence[:60] or "пусто",
        ),
    )

    advice_sentences = [s for s in _SENTENCE_SPLIT.split(advice) if s.strip()]
    results.append(
        CheckResult(
            "single_advice_sentence",
            len(advice_sentences) == 1,
            f"{len(advice_sentences)} предл.",
        ),
    )

    return results


def checklist_passed(results: list[CheckResult]) -> bool:
    return all(item.passed for item in results)
