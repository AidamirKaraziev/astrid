"""Карта дня: лимит, вытягивание, LLM-интерпретация через конфликт прогноза."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger
from astra.llm.daily_llm import get_daily_provider
from astra.llm.prompts.astrid import sanitize_prediction_output
from astra.llm.prompts.tarot_daily import (
    TAROT_SYSTEM_PROMPT,
    build_tarot_user_message,
    normalize_tarot_blocks,
    validate_tarot_output,
)
from astra.llm.types import ChatMessage, CompletionRequest
from astra.predictions import crud as predictions_crud
from astra.tarot import models as tarot_crud
from astra.tarot.deck import TarotCard, card_by_id
from astra.tarot.draw import draw_card
from astra.tarot.models import TarotDraw
from astra.users.models import User

log = get_logger(__name__)

_LOCK_TTL_SEC = 90
_TAROT_TEMPERATURE = 0.8
_TAROT_MAX_TOKENS = 450


@dataclass(frozen=True, slots=True)
class TarotRevealOutcome:
    draw: TarotDraw | None
    card: TarotCard | None
    already_drawn: bool = False
    failure_reason: str | None = None


def _conflict_text_from_context(astro_context: dict) -> str | None:
    conflict = astro_context.get("conflict")
    if isinstance(conflict, dict):
        return f"{conflict.get('side_a')} vs {conflict.get('side_b')}"
    return None


_GENERATE_ATTEMPTS = 2


async def _generate_interpretation(
    card: TarotCard,
    astro_context: dict,
    settings: Settings,
) -> tuple[str | None, str]:
    provider = get_daily_provider(settings)
    request = CompletionRequest(
        messages=(
            ChatMessage("system", TAROT_SYSTEM_PROMPT),
            ChatMessage("user", build_tarot_user_message(card, astro_context)),
        ),
        temperature=_TAROT_TEMPERATURE,
        max_tokens=_TAROT_MAX_TOKENS,
        timeout_seconds=settings.deepseek_timeout_seconds,
        extra={"thinking_disabled": True} if provider.name == "deepseek" else {},
    )
    last_error = "unknown"
    for _ in range(_GENERATE_ATTEMPTS):
        result = await provider.complete(request)
        if not result.text:
            last_error = result.reason or "empty_response"
            continue
        cleaned = sanitize_prediction_output(result.text) or result.text.strip()
        cleaned = normalize_tarot_blocks(cleaned)
        validation_error = validate_tarot_output(cleaned)
        if validation_error is None:
            return cleaned, ""
        last_error = validation_error
    return None, last_error


async def reveal_daily_card(
    session: AsyncSession,
    user: User,
    target: date_type,
    settings: Settings | None = None,
) -> TarotRevealOutcome:
    """Идемпотентно: повторное нажатие возвращает уже вытянутую карту."""
    cfg = settings or get_settings()

    existing = await tarot_crud.get_daily_draw(session, user.id, target)
    if existing is not None:
        log.info(Event.TAROT_LIMIT_HIT, user_id=user.id)
        return TarotRevealOutcome(
            draw=existing,
            card=card_by_id(existing.card_id),
            already_drawn=True,
        )

    lock_key = f"astra:tarot:daily:{user.id}:{target.isoformat()}"
    client = Redis.from_url(cfg.redis_url, decode_responses=True)
    try:
        acquired = await client.set(lock_key, "1", nx=True, ex=_LOCK_TTL_SEC)
        if not acquired:
            return TarotRevealOutcome(draw=None, card=None, failure_reason="in_progress")

        prediction = await predictions_crud.get_prediction_for_date(session, user.id, target)
        astro_context = (prediction.astro_context if prediction else None) or {}

        previous = await tarot_crud.get_previous_draw(session, user.id)
        exclude = frozenset({previous.card_id}) if previous else frozenset()
        card = draw_card(exclude_ids=exclude)

        interpretation, failure = await _generate_interpretation(card, astro_context, cfg)
        if interpretation is None:
            log.error(Event.TAROT_INTERPRET_FAILED, user_id=user.id, reason=failure)
            return TarotRevealOutcome(draw=None, card=card, failure_reason=failure)

        draw = await tarot_crud.create_draw(
            session,
            user_id=user.id,
            target=target,
            card_id=card.id,
            conflict_text=_conflict_text_from_context(astro_context),
            interpretation=interpretation,
        )
        log.info(Event.TAROT_CARD_DRAWN, user_id=user.id, card_id=card.id)
        return TarotRevealOutcome(draw=draw, card=card)
    finally:
        await client.delete(lock_key)
        await client.aclose()


def format_tarot_reveal(card: TarotCard, interpretation: str, *, repeated: bool = False) -> str:
    """HTML сообщения раскрытия карты."""
    blocks = [b.strip() for b in interpretation.split("\n\n") if b.strip()]
    body = blocks[0] if blocks else interpretation
    step = " ".join(blocks[1:]) if len(blocks) > 1 else ""

    if repeated:
        head = (
            f"🎴 Колода уже ответила тебе сегодня — <b>{card.name_ru}</b> {card.emoji}\n"
            "Вторая карта в один день путает нити. Вот её слова ещё раз:"
        )
    else:
        head = (
            "🎴 <b>Я спросила карты о твоей развилке.</b>\n"
            f"Выпала <b>{card.name_ru}</b> {card.emoji}"
        )

    lines = [head, "", body]
    if step:
        lines += ["", f"→ <b>Один шаг:</b> {step}"]
    return "\n".join(lines)
