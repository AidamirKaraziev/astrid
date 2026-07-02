"""Обрезка текста под лимиты PDF без рваных слов."""

from __future__ import annotations


def clamp_text(text: str, max_len: int, *, ellipsis: str = "…") -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_len:
        return cleaned
    if max_len <= len(ellipsis):
        return ellipsis[:max_len]

    cut = cleaned[: max_len - len(ellipsis)]
    for sep in ".!?":
        idx = cut.rfind(sep)
        if idx >= int(max_len * 0.45):
            return cut[: idx + 1].strip() + ellipsis
    if " " in cut:
        return cut.rsplit(" ", 1)[0].strip() + ellipsis
    return cut.strip() + ellipsis
