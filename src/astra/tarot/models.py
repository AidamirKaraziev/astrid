"""История вытянутых карт: карта дня (TarotDraw) и платные расклады (TarotReading)."""

from __future__ import annotations

import uuid
from datetime import UTC, date as date_type, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from astra.db.base import Base, TimestampMixin
from astra.tarot.enums import ReadingStatus

CONTEXT_DAILY_CONFLICT = "daily_conflict"


class TarotDraw(Base, TimestampMixin):
    __tablename__ = "tarot_draws"
    __table_args__ = (
        UniqueConstraint("user_id", "date", "context_kind", name="uq_tarot_draw_user_date_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    date: Mapped[date_type] = mapped_column(Date, index=True)
    context_kind: Mapped[str] = mapped_column(String(32), default=CONTEXT_DAILY_CONFLICT)
    card_id: Mapped[str] = mapped_column(String(32))
    reversed: Mapped[bool] = mapped_column(Boolean, default=False)
    conflict_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)


async def get_daily_draw(
    session: AsyncSession,
    user_id: uuid.UUID,
    target: date_type,
    *,
    context_kind: str = CONTEXT_DAILY_CONFLICT,
) -> TarotDraw | None:
    result = await session.execute(
        select(TarotDraw).where(
            TarotDraw.user_id == user_id,
            TarotDraw.date == target,
            TarotDraw.context_kind == context_kind,
        ),
    )
    return result.scalar_one_or_none()


async def get_previous_draw(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    context_kind: str = CONTEXT_DAILY_CONFLICT,
) -> TarotDraw | None:
    result = await session.execute(
        select(TarotDraw)
        .where(TarotDraw.user_id == user_id, TarotDraw.context_kind == context_kind)
        .order_by(TarotDraw.date.desc())
        .limit(1),
    )
    return result.scalar_one_or_none()


class TarotReading(Base, TimestampMixin):
    """Платный расклад: вопрос → оплата Stars → карты → LLM-интерпретация → доставка.

    price_stars/paid_at заполняются при оплате; NULL = черновик (pending_payment).
    Финансовый документ — таблица payments; здесь только снапшот для удобства.
    """

    __tablename__ = "tarot_readings"
    __table_args__ = (Index("ix_tarot_readings_user_date", "user_id", "date"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    date: Mapped[date_type] = mapped_column(Date)  # локальная дата юзера — для лимита
    spread_type: Mapped[str] = mapped_column(String(32))
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{"position": 1, "position_key": "past", "card_id": "wands_03", "reversed": false}]
    cards: Mapped[list] = mapped_column(JSONB)
    interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=ReadingStatus.PENDING)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_stars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


async def get_reading(session: AsyncSession, reading_id: uuid.UUID) -> TarotReading | None:
    result = await session.execute(select(TarotReading).where(TarotReading.id == reading_id))
    return result.scalar_one_or_none()


async def create_reading(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    target: date_type,
    spread_type: str,
    question: str | None,
    cards: list[dict],
    status: ReadingStatus = ReadingStatus.PENDING,
) -> TarotReading:
    row = TarotReading(
        user_id=user_id,
        date=target,
        spread_type=spread_type,
        question=question,
        cards=cards,
        status=status,
    )
    session.add(row)
    await session.flush()
    return row


async def mark_reading_sent(session: AsyncSession, reading: TarotReading) -> None:
    reading.status = ReadingStatus.READY
    reading.sent_at = datetime.now(UTC)
    await session.flush()


async def create_draw(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    target: date_type,
    card_id: str,
    conflict_text: str | None,
    interpretation: str | None,
    context_kind: str = CONTEXT_DAILY_CONFLICT,
) -> TarotDraw:
    row = TarotDraw(
        user_id=user_id,
        date=target,
        context_kind=context_kind,
        card_id=card_id,
        reversed=False,
        conflict_text=conflict_text,
        interpretation=interpretation,
    )
    session.add(row)
    await session.flush()
    return row
