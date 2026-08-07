"""Агент Astrid: свободный текст → структурированное намерение.

Тонкая обёртка вокруг существующего LLM-слоя (`get_llm_provider`).
Не тянет новых зависимостей: используем тот же DeepSeek и его `json_mode`
(`response_format={"type": "json_object"}`), что уже работает в совместимости.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from astra.core.config import Settings, get_settings
from astra.core.observability import get_logger
from astra.llm.factory import get_llm_provider
from astra.llm.types import ChatMessage, CompletionRequest
from astra.telegram.ai_chat.intents import AstridReply, Intent
from astra.telegram.ai_chat.prompt import build_system_prompt

log = get_logger(__name__)

# Сколько последних реплик диалога держим в контексте (роль/контент пары).
_HISTORY_LIMIT = 12


def _fallback(reason: str) -> AstridReply:
    """Если LLM недоступен или вернул мусор — не падаем, отвечаем по-человечески."""
    log.warning("ai_chat.fallback", reason=reason)
    return AstridReply(
        reply="Немного потерялась в звёздах ✨ Повтори, что ты хочешь?",
        intent=Intent.smalltalk,
        ready_to_route=False,
    )


def _parse(raw: str) -> AstridReply:
    # DeepSeek в json_mode возвращает чистый объект, но подстрахуемся от ```json обёртки.
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") : text.rfind("}") + 1]
    try:
        return AstridReply.model_validate_json(text)
    except (ValidationError, json.JSONDecodeError) as exc:
        return _fallback(f"parse:{type(exc).__name__}")


async def run_astrid(
    history: list[dict[str, str]],
    user_text: str,
    *,
    user_name: str | None = None,
    settings: Settings | None = None,
) -> AstridReply:
    """Прогнать одну реплику пользователя через Astrid.

    `history` — предыдущие пары {"role": "user"|"assistant", "content": ...}.
    Возвращает структурированный `AstridReply`, готовый к роутингу.
    """
    cfg = settings or get_settings()
    provider = get_llm_provider(cfg.ai_chat_provider, cfg, purpose="ai_chat")

    messages: list[ChatMessage] = [
        ChatMessage(role="system", content=build_system_prompt(user_name)),
    ]
    for turn in history[-_HISTORY_LIMIT:]:
        messages.append(ChatMessage(role=turn["role"], content=turn["content"]))
    messages.append(ChatMessage(role="user", content=user_text))

    request = CompletionRequest(
        messages=tuple(messages),
        temperature=0.4,
        max_tokens=700,
        extra={"json_mode": True, "thinking_disabled": True},
    )

    result = await provider.complete(request)
    if not result.text:
        return _fallback(result.reason or "empty")
    return _parse(result.text)
