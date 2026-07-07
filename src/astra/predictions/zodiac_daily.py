"""Общий гороскоп по знаку на день: генерация DeepSeek + кэш в БД.

Для «бесплатного» тарифа (personal_predictions_enabled=false): один текст
на знак в сутки, максимум 12 LLM-вызовов в день. Генерация ленивая —
первый пользователь знака триггерит её под Redis-локом.
"""

from __future__ import annotations

import json
import uuid
from datetime import date as date_type
from textwrap import dedent

from redis.asyncio import Redis
from sqlalchemy import Date, String, Text, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from astra.astro.daily_context import TRANSIT_ORB_LIMITS, _match_aspect, _transit_positions
from astra.astro.constants import POINT_EN_TO_RU, SIGN_EN_TO_RU, SIGN_RU_PREPOSITIONAL
from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger
from astra.db.base import Base, TimestampMixin
from astra.llm.daily_llm import get_daily_provider
from astra.llm.prompts.astrid import (
    sanitize_prediction_output,
    validate_prediction_output,
)
from astra.llm.types import ChatMessage, CompletionRequest

log = get_logger(__name__)

ZODIAC_SIGNS_RU: tuple[str, ...] = tuple(SIGN_EN_TO_RU.values())

# эталонная точка знака — 15° (середина)
_SIGN_MID_LON: dict[str, float] = {
    sign: idx * 30.0 + 15.0 for idx, sign in enumerate(ZODIAC_SIGNS_RU)
}

_LOCK_TTL_SEC = 120
_MOSCOW = (55.75, 37.62, "Europe/Moscow")


class ZodiacDailyHoroscope(Base, TimestampMixin):
    __tablename__ = "zodiac_daily_horoscopes"
    __table_args__ = (UniqueConstraint("sign", "date", name="uq_zodiac_daily_sign_date"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    sign: Mapped[str] = mapped_column(String(32), index=True)
    date: Mapped[date_type] = mapped_column(Date, index=True)
    text: Mapped[str] = mapped_column(Text)
    moon_note: Mapped[str | None] = mapped_column(String(128), nullable=True)


async def get_zodiac_daily(
    session: AsyncSession,
    sign: str,
    target: date_type,
) -> ZodiacDailyHoroscope | None:
    result = await session.execute(
        select(ZodiacDailyHoroscope).where(
            ZodiacDailyHoroscope.sign == sign,
            ZodiacDailyHoroscope.date == target,
        ),
    )
    return result.scalar_one_or_none()


_ZODIAC_SYSTEM_PROMPT = dedent(
    """
    Ты — Astrid, астролог в Telegram-боте Astra.
    Пишешь короткий гороскоп на день для ЗНАКА ЗОДИАКА по реальным транзитам
    этого дня. Тёпло, честно, без запугивания. Обращение на «ты».

    Правила:
    - Опирайся только на данные из сообщения: аспекты дня к точке знака,
      положение и фаза Луны.
    - Переводи астрологию на быт: чувства, разговоры, дела, тело.
      Планету можно назвать один раз.
    - Без общих фраз, подходящих любому знаку в любой день. Запрещено:
      «вас ждут перемены», «будьте внимательны», «звёзды советуют»,
      «космос подсказывает», «энергетика», «гармония», «вибрации».
    - Не пугай и не обещай наверняка.
    Язык: только русский.

    Формат ответа (строго, три блока через пустую строку):

    [вопрос дня — одна строка 15–65 символов, с «?»]

    [3–4 предложения прогноза для знака]

    [один шаг — одно предложение, конкретное действие]
    """,
).strip()


def build_zodiac_user_message(sign: str, target: date_type) -> tuple[str, str | None]:
    """User message + заметка о Луне (для шапки сообщения)."""
    lat, lon, tz = _MOSCOW
    positions, moon_phase, moon_sign = _transit_positions(target, lat=lat, lon=lon, timezone=tz)

    ref_lon = _SIGN_MID_LON[sign]
    aspects = []
    for planet_key, planet_lon in positions.items():
        limit = TRANSIT_ORB_LIMITS.get(planet_key)
        if limit is None:
            continue
        match = _match_aspect(planet_lon, ref_lon, limit)
        if match is None:
            continue
        aspect_en, orb = match
        from astra.astro.constants import ASPECT_EN_TO_RU

        aspects.append(
            {
                "транзит": POINT_EN_TO_RU.get(planet_key, planet_key),
                "аспект": ASPECT_EN_TO_RU[aspect_en],
                "орб": round(orb, 2),
            },
        )
    aspects.sort(key=lambda a: a["орб"])

    moon_note = None
    if moon_sign:
        moon_note = f"Луна в {SIGN_RU_PREPOSITIONAL.get(moon_sign, moon_sign)}"
        if moon_phase:
            moon_note += f", {moon_phase}"

    payload = {
        "знак": sign,
        "дата": target.isoformat(),
        "аспекты_дня_к_знаку": aspects[:3],
        "луна": {"знак": moon_sign, "фаза": moon_phase},
    }
    message = (
        f"Составь гороскоп на день для знака {sign}.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
    return message, moon_note


async def _generate_zodiac_text(
    sign: str,
    target: date_type,
    settings: Settings,
) -> tuple[str | None, str | None, str]:
    """(text, moon_note, failure_reason)."""
    provider = get_daily_provider(settings)
    user_message, moon_note = build_zodiac_user_message(sign, target)
    result = await provider.complete(
        CompletionRequest(
            messages=(
                ChatMessage("system", _ZODIAC_SYSTEM_PROMPT),
                ChatMessage("user", user_message),
            ),
            temperature=0.75,
            max_tokens=450,
            timeout_seconds=settings.deepseek_timeout_seconds,
            extra={"thinking_disabled": True} if provider.name == "deepseek" else {},
        ),
    )
    if not result.text:
        return None, moon_note, result.reason or "empty_response"
    cleaned = sanitize_prediction_output(result.text)
    if not cleaned:
        return None, moon_note, "sanitize_empty"
    validation_error = validate_prediction_output(cleaned, "", require_name=False)
    if validation_error:
        return None, moon_note, validation_error
    return cleaned, moon_note, ""


async def get_or_generate_zodiac_daily(
    session: AsyncSession,
    sign: str,
    target: date_type,
    settings: Settings | None = None,
) -> ZodiacDailyHoroscope | None:
    """Кэшированный гороскоп знака; генерация под Redis-локом при отсутствии."""
    cfg = settings or get_settings()

    cached = await get_zodiac_daily(session, sign, target)
    if cached is not None:
        return cached

    lock_key = f"astra:zodiac_daily:lock:{sign}:{target.isoformat()}"
    client = Redis.from_url(cfg.redis_url, decode_responses=True)
    try:
        acquired = await client.set(lock_key, "1", nx=True, ex=_LOCK_TTL_SEC)
        if not acquired:
            # кто-то уже генерит — перечитать кэш (может успел)
            return await get_zodiac_daily(session, sign, target)

        text, moon_note, failure = await _generate_zodiac_text(sign, target, cfg)
        if text is None:
            log.error(Event.LLM_VALIDATION_FAILED, sign=sign, reason=failure, prompt_version="zodiac")
            return None

        row = ZodiacDailyHoroscope(sign=sign, date=target, text=text, moon_note=moon_note)
        session.add(row)
        await session.flush()
        return row
    finally:
        await client.delete(lock_key)
        await client.aclose()


ZODIAC_CTA = "✨ Хочешь прогноз по своей карте, а не по знаку? Скоро в Astra."
