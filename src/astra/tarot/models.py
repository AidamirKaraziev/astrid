"""История вытянутых карт: лимит «одна карта в день» + данные для будущей игры."""

from __future__ import annotations

import uuid
from datetime import date as date_type

from sqlalchemy import Boolean, Date, ForeignKey, String, Text, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from astra.db.base import Base, TimestampMixin

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
