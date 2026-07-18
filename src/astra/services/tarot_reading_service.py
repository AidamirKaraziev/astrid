"""Платные расклады: лимит, создание, LLM-интерпретация в worker, доставка.

Гибридный пайплайн: бот мгновенно показывает карты и публикует
tarot_reading.generate; worker генерирует интерпретацию (tarot_reading.send)
и шлёт текст через send_telegram_html. LLM в хендлерах бота не вызывается.
"""

from __future__ import annotations

from datetime import date as date_type, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger
from astra.llm.daily_llm import get_daily_provider
from astra.llm.prompts.tarot_spreads import TAROT_PRODUCTS
from astra.llm.types import ChatMessage, CompletionRequest
from astra.tarot import models as tarot_crud
from astra.tarot.deck import TarotCard, card_by_id
from astra.tarot.draw import draw_cards
from astra.tarot.enums import ReadingStatus
from astra.tarot.models import TarotReading
from astra.tarot.spreads import SPREADS, SpreadSpec, SpreadType
from astra.users import crud as users_crud
from astra.users.models import User
from astra.workers.telegram_send import send_telegram_html

log = get_logger(__name__)

PENDING_LOCK_TTL_SEC = 120
_TAROT_TEMPERATURE = 0.8
_GENERATE_ATTEMPTS = 2

READING_FAILED_TEXT = (
    "Карты легли, но их голоса сегодня спутались — расклад не сложился 🌙\n"
    "Эта попытка не считается: загляни через пару минут и спроси ещё раз."
)

LIMIT_HIT_TEXT = (
    "🎴 На сегодня карты уже разложены. Колоде нужно время, чтобы голоса карт "
    "не смешивались ✨\n"
    "Но если вопрос не ждёт — можно сделать ещё один расклад прямо сейчас 👇"
)

# Бонусные расклады сверх дневного лимита (пока выдаются бесплатно по кнопке).
# Живут в Redis до конца суток+, чтобы не плодить миграцию под временную механику.
_BONUS_TTL_SEC = 60 * 60 * 48


def _bonus_key(user_id: UUID, target: date_type) -> str:
    return f"astra:tarot:reading:bonus:{user_id}:{target.isoformat()}"


def local_today(user: User) -> date_type:
    return datetime.now(ZoneInfo(user.profile.timezone)).date()


async def granted_bonus(
    user_id: UUID,
    target: date_type,
    settings: Settings | None = None,
) -> int:
    """Сколько дополнительных раскладов уже выдано сверх лимита за этот день."""
    cfg = settings or get_settings()
    client = Redis.from_url(cfg.redis_url, decode_responses=True)
    try:
        value = await client.get(_bonus_key(user_id, target))
        return int(value) if value else 0
    finally:
        await client.aclose()


async def grant_bonus_reading(
    user_id: UUID,
    target: date_type,
    settings: Settings | None = None,
) -> int:
    """Выдать ещё один расклад сверх лимита; возвращает новое число бонусов."""
    cfg = settings or get_settings()
    client = Redis.from_url(cfg.redis_url, decode_responses=True)
    try:
        key = _bonus_key(user_id, target)
        new_value = await client.incr(key)
        await client.expire(key, _BONUS_TTL_SEC)
        return int(new_value)
    finally:
        await client.aclose()


async def check_daily_limit(
    session: AsyncSession,
    user: User,
    target: date_type,
    settings: Settings | None = None,
) -> bool:
    """True — можно тянуть; failed-расклады попытку не съедают.

    Эффективный лимит = базовый из конфига + бонусы, выданные по кнопке.
    """
    cfg = settings or get_settings()
    used = await tarot_crud.count_readings_for_date(session, user.id, target)
    bonus = await granted_bonus(user.id, target, cfg)
    return used < cfg.tarot_spreads_daily_limit + bonus


async def try_acquire_reading_lock(user_id: UUID, settings: Settings | None = None) -> bool:
    """Redis NX-лок от даблтапа, пока расклад создаётся и уходит в очередь."""
    cfg = settings or get_settings()
    client = Redis.from_url(cfg.redis_url, decode_responses=True)
    try:
        return bool(
            await client.set(
                f"astra:tarot:reading:pending:{user_id}",
                "1",
                nx=True,
                ex=PENDING_LOCK_TTL_SEC,
            ),
        )
    finally:
        await client.aclose()


async def release_reading_lock(user_id: UUID, settings: Settings | None = None) -> None:
    cfg = settings or get_settings()
    client = Redis.from_url(cfg.redis_url, decode_responses=True)
    try:
        await client.delete(f"astra:tarot:reading:pending:{user_id}")
    finally:
        await client.aclose()


async def create_reading(
    session: AsyncSession,
    user: User,
    spread_type: SpreadType,
    question: str | None,
    target: date_type,
) -> tuple[TarotReading, list[TarotCard]]:
    spec = SPREADS[spread_type]
    drawn = draw_cards(spec.card_count)
    cards_json = [
        {
            "position": index + 1,
            "position_key": position.key,
            "card_id": item.card.id,
            "reversed": item.reversed,
        }
        for index, (position, item) in enumerate(zip(spec.positions, drawn, strict=True))
    ]
    reading = await tarot_crud.create_reading(
        session,
        user_id=user.id,
        target=target,
        spread_type=spread_type,
        question=question,
        cards=cards_json,
    )
    log.info(
        Event.TAROT_READING_CREATED,
        user_id=user.id,
        reading_id=reading.id,
        spread_type=str(spread_type),
    )
    return reading, [item.card for item in drawn]


def reading_cards(reading: TarotReading) -> list[TarotCard]:
    cards = [card_by_id(entry["card_id"]) for entry in reading.cards]
    if any(card is None for card in cards):
        raise ValueError(f"неизвестная карта в раскладе {reading.id}")
    return cards  # type: ignore[return-value]


async def generate_reading_interpretation(
    session: AsyncSession,
    reading_id: UUID,
    settings: Settings | None = None,
) -> TarotReading | None:
    """None — расклад помечен failed (или не найден); иначе text_ready."""
    cfg = settings or get_settings()
    reading = await tarot_crud.get_reading(session, reading_id)
    if reading is None:
        return None
    if reading.interpretation and reading.status in (
        ReadingStatus.TEXT_READY,
        ReadingStatus.READY,
    ):
        return reading  # идемпотентность при requeue

    reading.status = ReadingStatus.GENERATING
    await session.flush()

    product = TAROT_PRODUCTS[SpreadType(reading.spread_type)]
    cards = reading_cards(reading)
    user = await users_crud.get_user_by_id(session, reading.user_id)
    profile = user.profile if user else None
    provider = get_daily_provider(cfg)
    extra: dict = {"json_mode": True}
    if provider.name == "deepseek":
        extra["thinking_disabled"] = True
    request = CompletionRequest(
        messages=(
            ChatMessage("system", product.system_prompt),
            ChatMessage(
                "user",
                product.build_user_message(
                    reading.question,
                    cards,
                    user_name=profile.display_name if profile else None,
                    gender=profile.gender if profile else None,
                ),
            ),
        ),
        temperature=_TAROT_TEMPERATURE,
        max_tokens=product.max_tokens,
        timeout_seconds=cfg.deepseek_timeout_seconds,
        extra=extra,
    )

    last_error = "unknown"
    for _ in range(_GENERATE_ATTEMPTS):
        result = await provider.complete(request)
        if not result.text:
            last_error = result.reason or "empty_response"
            continue
        data = product.parse(result.text)
        if data is None:
            last_error = "json_invalid"
            continue
        validation_error = product.validate(data)
        if validation_error is None:
            # Рендерим финальное сообщение сразу из структурированных полей —
            # позиция→текст детерминированы, съехать не может.
            reading.interpretation = product.render(reading.question, cards, data)
            reading.status = ReadingStatus.TEXT_READY
            await session.flush()
            log.info(Event.TAROT_READING_GENERATED, reading_id=reading.id)
            return reading
        last_error = validation_error

    reading.status = ReadingStatus.FAILED
    reading.failure_reason = last_error
    await session.flush()
    log.error(Event.TAROT_READING_FAILED, reading_id=reading.id, reason=last_error)
    return None


async def deliver_reading(
    session: AsyncSession,
    reading_id: UUID,
    settings: Settings | None = None,
) -> bool:
    """Идемпотентно: повторная доставка (requeue) не шлёт второе сообщение."""
    reading = await tarot_crud.get_reading(session, reading_id)
    if reading is None or reading.interpretation is None or reading.sent_at is not None:
        return False
    user = await users_crud.get_user_by_id(session, reading.user_id)
    if user is None:
        return False
    # interpretation уже содержит готовое HTML-сообщение (отрендерено при генерации).
    await send_telegram_html(user.telegram_id, reading.interpretation, settings)
    await tarot_crud.mark_reading_sent(session, reading)
    log.info(Event.TAROT_READING_SENT, reading_id=reading.id, user_id=user.id)
    return True


async def notify_reading_failed(
    session: AsyncSession,
    reading: TarotReading,
    settings: Settings | None = None,
) -> None:
    user = await users_crud.get_user_by_id(session, reading.user_id)
    if user is None:
        return
    await send_telegram_html(user.telegram_id, READING_FAILED_TEXT, settings)


def format_reading_caption(spec: SpreadSpec, cards: list[TarotCard]) -> str:
    """Caption к фото/альбому: заголовок и карты; интерпретация придёт отдельно."""
    lines = [f"{spec.emoji} <b>{spec.title_ru}</b>", ""]
    lines += [
        f"<b>{position.label_ru}:</b> {card.name_ru} {card.emoji}"
        for position, card in zip(spec.positions, cards, strict=True)
    ]
    lines += ["", "Астрид уже читает расклад — интерпретация будет через минуту 🕯"]
    return "\n".join(lines)
