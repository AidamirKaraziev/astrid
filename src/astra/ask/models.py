"""Ответы раздела «Спроси Астрид»: расчёт, разбор и их жизненный цикл.

Одна строка = один купленный ответ. В `computed` лежит воспроизводимый снимок
расчёта (числа + факторы + версия метода), в `answer` — разбор от LLM. Из этой
же таблицы отдаётся бесплатный архив: карта не меняется, значит и ответ один.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from astra.ask.enums import AskStatus
from astra.db.base import Base, TimestampMixin


class AskReading(Base, TimestampMixin):
    __tablename__ = "ask_readings"
    __table_args__ = (
        Index("ix_ask_readings_user_question", "user_id", "question_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    question_key: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default=AskStatus.PENDING_PAYMENT)
    # Ответ человека перед покупкой: сейчас в отношениях или свободен.
    in_relationship: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Снимок расчёта: числа, факторы, окна, версия метода.
    computed: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    methodology_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Разбор от LLM по схеме продукта.
    answer: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # file_id карточки в Telegram: переиспользуем при повторной выдаче из архива.
    card_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    paid_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # charge_id платежа: по нему возвращаем звёзды, если разбор не собрался.
    charge_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    refunded: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


async def create_draft(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    question_key: str,
    in_relationship: bool | None,
) -> AskReading:
    reading = AskReading(
        user_id=user_id,
        question_key=question_key,
        in_relationship=in_relationship,
        status=AskStatus.PENDING_PAYMENT,
    )
    session.add(reading)
    await session.flush()
    return reading


async def get_reading(session: AsyncSession, reading_id: uuid.UUID) -> AskReading | None:
    return await session.get(AskReading, reading_id)


async def get_ready_reading(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    question_key: str,
) -> AskReading | None:
    """Готовый ответ из архива: карта одна — ответ тоже один, отдаём бесплатно."""
    result = await session.execute(
        select(AskReading)
        .where(
            AskReading.user_id == user_id,
            AskReading.question_key == question_key,
            AskReading.status == AskStatus.READY,
        )
        .order_by(AskReading.created_at.desc())
        .limit(1),
    )
    return result.scalar_one_or_none()


async def mark_paid(
    session: AsyncSession,
    reading: AskReading,
    *,
    amount: int,
    charge_id: str | None,
    computed: dict[str, Any],
    methodology_version: int,
) -> None:
    reading.status = AskStatus.GENERATING
    reading.paid_amount = amount
    reading.charge_id = charge_id
    reading.computed = computed
    reading.methodology_version = methodology_version
    await session.flush()


async def mark_refunded(session: AsyncSession, reading: AskReading) -> None:
    reading.refunded = True
    await session.flush()


async def save_answer(session: AsyncSession, reading: AskReading, answer: dict[str, Any]) -> None:
    reading.answer = answer
    reading.status = AskStatus.READY
    await session.flush()


async def mark_failed(session: AsyncSession, reading: AskReading, error: str) -> None:
    reading.status = AskStatus.FAILED
    reading.error = error[:500]
    await session.flush()


async def save_card_file_id(session: AsyncSession, reading: AskReading, file_id: str) -> None:
    reading.card_file_id = file_id
    await session.flush()
