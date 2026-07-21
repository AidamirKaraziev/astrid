"""Карта дня: утренняя рассылка карты и прогноз по кнопке.

Бесплатный ежедневный продукт вместо астро-предсказания. Утром worker тянет
карту и шлёт фото с кнопкой «Что это значит для меня»; LLM вызывается только
при нажатии — прогноз пишется в tarot_draws.forecast и переиспользуется при
повторных нажатиях.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date as date_type, datetime

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger
from astra.llm.daily_llm import get_daily_provider
from astra.llm.prompts import day_card as day_card_prompt
from astra.llm.types import ChatMessage, CompletionRequest
from astra.predictions import crud as predictions_crud
from astra.tarot import models as tarot_crud
from astra.tarot.deck import TarotCard, card_by_id
from astra.tarot.draw import draw_card
from astra.tarot.models import CONTEXT_DAY_CARD, TarotDraw
from astra.users.models import User

log = get_logger(__name__)

_FORECAST_LOCK_TTL_SEC = 90
_TEMPERATURE = 0.8
_GENERATE_ATTEMPTS = 2

FORECAST_FAILED_TEXT = (
    "Карта на месте, а слова сегодня не складываются 🌙\n"
    "Нажми кнопку ещё раз через минуту."
)


def _first_sentence(text: str) -> str:
    """Крючок под картинкой — первая фраза «голоса карты» из колоды."""
    for end in (". ", "! ", "? "):
        head, sep, _ = text.partition(end)
        if sep:
            return (head + sep.strip()).strip()
    return text.strip()


def format_card_caption(card: TarotCard) -> str:
    """Подпись к фото карты: название и одна фраза — смысл остаётся за кнопкой."""
    return (
        f"🎴 Твоя карта на сегодня — <b>{card.name_ru}</b>\n"
        f"<i>{_first_sentence(card.voice)}</i>"
    )


async def get_day_card(
    session: AsyncSession,
    user_id,  # noqa: ANN001 — UUID
    target: date_type,
) -> TarotDraw | None:
    return await tarot_crud.get_daily_draw(
        session,
        user_id,
        target,
        context_kind=CONTEXT_DAY_CARD,
    )


async def ensure_day_card(
    session: AsyncSession,
    user: User,
    target: date_type,
) -> tuple[TarotDraw, TarotCard]:
    """Идемпотентно: карта на дату тянется один раз, вчерашняя не повторяется."""
    existing = await get_day_card(session, user.id, target)
    if existing is not None:
        card = card_by_id(existing.card_id)
        if card is not None:
            return existing, card

    previous = await tarot_crud.get_previous_draw(session, user.id, context_kind=CONTEXT_DAY_CARD)
    exclude = frozenset({previous.card_id}) if previous else frozenset()
    card = draw_card(exclude_ids=exclude)
    draw = await tarot_crud.create_draw(
        session,
        user_id=user.id,
        target=target,
        card_id=card.id,
        conflict_text=None,
        interpretation=None,
        context_kind=CONTEXT_DAY_CARD,
    )
    log.info(Event.TAROT_CARD_DRAWN, user_id=user.id, card_id=card.id)
    return draw, card


async def _astro_context(session: AsyncSession, user_id, target: date_type) -> dict:  # noqa: ANN001
    prediction = await predictions_crud.get_prediction_for_date(session, user_id, target)
    return (prediction.astro_context if prediction else None) or {}


async def _complete(
    card: TarotCard,
    astro_context: dict,
    user: User,
    cfg: Settings,
) -> tuple[day_card_prompt.DayCardReading | None, str]:
    provider = get_daily_provider(cfg)
    extra: dict = {"json_mode": True}
    if provider.name == "deepseek":
        extra["thinking_disabled"] = True
    profile = user.profile
    request = CompletionRequest(
        messages=(
            ChatMessage("system", day_card_prompt.SYSTEM_PROMPT),
            ChatMessage(
                "user",
                day_card_prompt.build_user_message(
                    card,
                    astro_context,
                    user_name=profile.display_name if profile else None,
                    gender=profile.gender if profile else None,
                ),
            ),
        ),
        temperature=_TEMPERATURE,
        max_tokens=day_card_prompt.MAX_TOKENS,
        timeout_seconds=cfg.deepseek_timeout_seconds,
        extra=extra,
    )

    last_error = "unknown"
    for _attempt in range(_GENERATE_ATTEMPTS):
        result = await provider.complete(request)
        if not result.text:
            last_error = result.reason or "empty_response"
            continue
        data = day_card_prompt.parse(result.text)
        if data is None:
            last_error = "json_invalid"
            continue
        validation_error = day_card_prompt.validate(data)
        if validation_error is None:
            return data, ""
        last_error = validation_error
    return None, last_error


async def deliver_day_card(
    session: AsyncSession,
    user: User,
    target: date_type,
    settings: Settings | None = None,
) -> TarotCard:
    """Утренняя рассылка: фото карты + кнопка. LLM здесь не вызывается."""
    from astra.tarot.images import image_path
    from astra.telegram.keyboards import day_card_keyboard
    from astra.workers.telegram_send import send_card_photo_to_telegram

    _draw, card = await ensure_day_card(session, user, target)
    await send_card_photo_to_telegram(
        user.telegram_id,
        card.id,
        image_path(card.id),
        caption=format_card_caption(card),
        reply_markup=day_card_keyboard(),
        settings=settings,
    )
    log.info(Event.DAY_CARD_SENT, user_id=user.id, card_id=card.id)
    return card


@dataclass(frozen=True, slots=True)
class DayForecastOutcome:
    """text — готовое HTML-сообщение; failure_reason: in_progress | причина LLM."""

    text: str | None
    failure_reason: str | None = None


async def build_day_forecast(
    session: AsyncSession,
    user: User,
    target: date_type,
    settings: Settings | None = None,
) -> DayForecastOutcome:
    """Идемпотентно: сохранённый прогноз возвращается без обращения к LLM.

    Redis-лок защищает от двойного нажатия кнопки: параллельный вызов получает
    in_progress и молчит, а не пишет второй прогноз.
    """
    cfg = settings or get_settings()
    draw, card = await ensure_day_card(session, user, target)
    if draw.forecast:
        return DayForecastOutcome(text=draw.forecast)

    lock_key = f"astra:daycard:forecast:{user.id}:{target.isoformat()}"
    client = Redis.from_url(cfg.redis_url, decode_responses=True)
    try:
        if not await client.set(lock_key, "1", nx=True, ex=_FORECAST_LOCK_TTL_SEC):
            return DayForecastOutcome(text=None, failure_reason="in_progress")
        astro_context = await _astro_context(session, user.id, target)
        data, failure = await _complete(card, astro_context, user, cfg)
        if data is None:
            log.error(Event.DAY_CARD_FORECAST_FAILED, user_id=user.id, reason=failure)
            return DayForecastOutcome(text=None, failure_reason=failure)
        draw.forecast = day_card_prompt.render(card, target, astro_context, data)
        draw.forecast_sent_at = datetime.now(UTC)
        await session.flush()
        log.info(Event.DAY_CARD_FORECAST_SENT, user_id=user.id, card_id=card.id)
        return DayForecastOutcome(text=draw.forecast)
    finally:
        await client.delete(lock_key)
        await client.aclose()
