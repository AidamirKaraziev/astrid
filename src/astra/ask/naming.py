"""Обращение по имени — целиком на стороне кода.

Модель имени не видит вовсе: она пишет обычный текст, а имя вставляет код при
рендере. Так имя звучит ровно там, где задумано, не «сыплется» по всему ответу
и не может быть просклонено криво.

В профиле лежит Telegram `first_name`, а это не всегда имя: бывает ник
латиницей, эмодзи или подстановка «друг». Такое к человеку не приложишь —
здесь одно место, которое решает, звать ли по имени вообще.
"""

from __future__ import annotations

import re

from astra.astro.constants import PLANET_EN_TO_RU, POINT_EN_TO_RU, SIGN_EN_TO_RU

_NAME_RE = re.compile(r"^[А-ЯЁа-яё]+(?:-[А-ЯЁа-яё]+)?$")
_MIN_LEN = 2
_MAX_LEN = 20

# Подстановки и самоназвания, которые именем не являются.
_NOT_NAMES = frozenset({"друг", "подруга", "гость", "гостья", "астрид", "юзер", "user"})


def addressable_name(raw: str | None) -> str | None:
    """Имя, которым можно позвать вслух. None — пишем без обращения."""
    if not raw:
        return None
    first = raw.strip().split()[0] if raw.strip() else ""
    # Эмодзи и знаки вокруг имени («Аня🌸», «*Аня*») отбрасываем, цифры — нет:
    # имя с цифрой именем не является, и такую строку надо отбраковать целиком.
    cleaned = first.strip("*_~`.,:;!?()[]{}«»\"'-—–")
    if not _MIN_LEN <= len(cleaned) <= _MAX_LEN or not _NAME_RE.match(cleaned):
        return None
    if cleaned.lower() in _NOT_NAMES:
        return None
    # Двойные имена пишутся с двух заглавных: «Анна-Мария», не «Анна-мария».
    return "-".join(part[0].upper() + part[1:].lower() for part in cleaned.split("-") if part)


# Слова, которые остаются с заглавной даже после обращения: «Аня, Венера в
# твоей карте…». Без этого списка код превратил бы их в «венера».
_KEEP_CAPITALIZED: frozenset[str] = frozenset(
    {
        *SIGN_EN_TO_RU.values(),
        *PLANET_EN_TO_RU.values(),
        *POINT_EN_TO_RU.values(),
        "Астрид",
        "Луна",
        "Солнце",
    },
)


def address(text: str, name: str | None) -> str:
    """«Аня, продолжение фразы».

    Текст пишется как продолжение обращения, со строчной. Имени нет — код
    поднимает первую букву, и фраза читается как обычное предложение.
    """
    stripped = text.strip()
    if not stripped:
        return stripped
    if not name:
        return stripped[0].upper() + stripped[1:]
    return f"{name}, {_lower_first(stripped)}"


def sentence(text: str) -> str:
    """Обычное предложение с заглавной.

    Страховка от того, что модель распространит правило «заход пишется со
    строчной» на остальные блоки: правило про заход, а не про весь ответ.
    """
    stripped = text.strip()
    return stripped[0].upper() + stripped[1:] if stripped else stripped


def _lower_first(text: str) -> str:
    """Строчная первая буква — кроме имён планет и знаков."""
    first_word = text.split(maxsplit=1)[0].strip(".,:;!?»«\"'")
    if first_word in _KEEP_CAPITALIZED:
        return text
    return text[0].lower() + text[1:]
