"""Разбивка длинного сообщения на части по границам блоков.

Telegram не принимает `sendMessage` длиннее 4096 знаков и отвечает
`400 Bad Request: message is too long`. Платный разбор растёт вместе с
данными человека (у «судьбоносных партнёров» — по блоку на партнёра), и
верхней границы у него нет ни в схеме ответа, ни в промпте.

Обрезать хвост нельзя: там итог и конкретное действие — то, за что заплатили.
Поэтому режем на несколько сообщений, и режем по пустой строке, чтобы блок
разбора не разрывался посередине.
"""

from __future__ import annotations

TELEGRAM_MESSAGE_LIMIT = 4096


def _safe_cut(window: str) -> int:
    """Куда резать, если ни абзацев, ни переводов строк не нашлось.

    Единственная забота — не разрубить тег пополам: `<b` в одной части и `>`
    в другой Telegram не поймёт. Пары тегов такой разрез пережить не может,
    но до него доходит только сплошная простыня без единого перевода строки —
    у наших разборов каждый блок пишется отдельной строкой.
    """
    opened = window.rfind("<")
    closed = window.rfind(">")
    return opened if opened > closed else len(window)


def split_html_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Части в порядке отправки. Короткий текст возвращается как есть."""
    if len(text) <= limit:
        return [text]

    parts: list[str] = []
    rest = text
    while len(rest) > limit:
        window = rest[:limit]
        cut = window.rfind("\n\n")
        if cut <= 0:
            cut = window.rfind("\n")
        if cut <= 0:
            cut = _safe_cut(window)
        head = rest[:cut].rstrip()
        if head:
            parts.append(head)
        rest = rest[cut:].lstrip("\n")

    if rest.strip():
        parts.append(rest)
    return parts
