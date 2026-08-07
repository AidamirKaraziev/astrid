"""ИИ-редактор рассылки и проверка разметки перед отправкой.

Модель ошибается предсказуемо: лишний тег, markdown вместо HTML, эмодзи из
интерфейсной палитры. Всё это ломает отправку не одному человеку, а всей
аудитории сразу — поэтому результат проверяется и чистится, а не уходит как есть.

Редактор можно выключить: тогда текст автора идёт без изменений, но через ту же
проверку разметки — опечатка в теге стоит одинаково дорого, кто бы её ни сделал.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from astra.core.observability import get_logger
from astra.core.config import get_settings
from astra.llm.factory import get_llm_provider
from astra.llm.prompts.broadcast import (
    FORBIDDEN_EMOJI,
    MAX_LENGTH,
    SYSTEM_PROMPT,
    build_user_message,
)
from astra.llm.types import ChatMessage, CompletionRequest

log = get_logger(__name__)

# Теги, которые Telegram понимает в parse_mode=HTML. Остальные — ошибка отправки.
ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
                "a", "code", "pre", "blockquote", "tg-spoiler", "span"}

_TAG_RE = re.compile(r"</?([a-zA-Z\-]+)[^>]*>")
_MARKDOWN_RE = re.compile(r"(\*\*|__|\[[^\]]+\]\([^)]+\))")


@dataclass(frozen=True, slots=True)
class Draft:
    """Готовое сообщение и то, что стоит показать автору перед отправкой."""

    text: str
    warnings: tuple[str, ...] = ()

    @property
    def length(self) -> int:
        return len(self.text)


def check(text: str) -> tuple[str, ...]:
    """Что не так с разметкой. Пустой кортеж — можно отправлять."""
    problems: list[str] = []

    unknown = {tag.lower() for tag in _TAG_RE.findall(text)} - ALLOWED_TAGS
    if unknown:
        problems.append(f"Telegram не поймёт теги: {', '.join(sorted(unknown))}")

    for tag in ALLOWED_TAGS:
        opened = len(re.findall(rf"<{tag}(?:\s[^>]*)?>", text, re.IGNORECASE))
        closed = len(re.findall(rf"</{tag}>", text, re.IGNORECASE))
        if opened != closed:
            problems.append(f"тег <{tag}> открыт {opened} раз, закрыт {closed}")

    if _MARKDOWN_RE.search(text):
        problems.append("похоже на markdown — Telegram покажет звёздочки как есть")

    forbidden = [emoji for emoji in FORBIDDEN_EMOJI.split() if emoji in text]
    if forbidden:
        problems.append(f"значки тащат чужой контекст: {' '.join(forbidden)}")

    if len(text) > MAX_LENGTH * 1.5:
        problems.append(f"длинновато: {len(text)} знаков, читается хуже короткого")

    if not text.strip():
        problems.append("пустое сообщение")

    return tuple(problems)


async def improve(
    draft: str,
    *,
    audience_note: str = "",
    personalize: bool = False,
) -> Draft:
    """Переписать черновик голосом Астрид. При отказе модели вернётся исходник."""
    cfg = get_settings()
    # Тот же провайдер, что и у остальных текстов бота: голос должен совпадать.
    provider = get_llm_provider(cfg.ai_chat_provider or "deepseek", cfg, purpose="broadcast")
    request = CompletionRequest(
        messages=(
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=build_user_message(
                    draft,
                    audience_note=audience_note,
                    personalize=personalize,
                ),
            ),
        ),
        temperature=0.8,
        max_tokens=900,
    )

    result = await provider.complete(request)
    if not result.text:
        log.warning("broadcast.improve_failed", reason=result.reason or "empty")
        return Draft(
            text=draft,
            warnings=("модель не ответила — текст остался твоим", *check(draft)),
        )

    text = result.text.strip()
    # Модель любит обернуть ответ в кавычки или в блок кода — снимаем.
    text = re.sub(r"^```(?:html)?\n?|```$", "", text).strip()
    if len(text) > 1 and text[0] == text[-1] == '"':
        text = text[1:-1].strip()

    return Draft(text=text, warnings=check(text))


def personalize_text(text: str, name: str | None) -> str:
    """Подставить имя в начало. Без имени сообщение остаётся как есть."""
    if not name:
        return text
    clean = name.strip()
    if not clean:
        return text
    first, _, rest = text.partition("\n")
    return f"{clean}, {first[0].lower()}{first[1:]}\n{rest}" if first else text
