"""Склонение имён и слов по падежам (русский)."""

from __future__ import annotations

from functools import lru_cache

from pymorphy3 import MorphAnalyzer

_CASE_LABELS: dict[str, str] = {
    "nomn": "именительный",
    "gent": "родительный",
    "datv": "дательный",
    "accs": "винительный",
    "ablt": "творительный",
    "loct": "предложный",
}


@lru_cache(maxsize=1)
def _morph() -> MorphAnalyzer:
    return MorphAnalyzer()


def _preserve_case(source: str, inflected: str) -> str:
    if not source or not inflected:
        return inflected
    if source[:1].isupper():
        return inflected[:1].upper() + inflected[1:]
    return inflected


def _first_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        return cleaned
    return cleaned.split()[0]


def inflect_name(name: str, case: str) -> str:
    """Склонить имя; при неудаче вернуть исходное."""
    word = _first_name(name)
    if not word:
        return name.strip()
    parsed = _morph().parse(word)
    if not parsed:
        return word
    form = parsed[0].inflect({case})
    if form is None:
        return word
    return _preserve_case(word, form.word)


def format_name_cases(name: str) -> str:
    """Строка с падежами для промпта LLM."""
    word = _first_name(name)
    if not word:
        return "имя не указано"
    parts = [f"{label}: {inflect_name(word, case)}" for case, label in _CASE_LABELS.items()]
    return "; ".join(parts)
