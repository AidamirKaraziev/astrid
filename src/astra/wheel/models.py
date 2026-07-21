"""Колесо фортуны: пул призов и выигрыши пользователей.

Пул (wheel_prizes) — админский справочник: товар + скидка + вес; управление
строками через SQL. Выигрыш (wheel_wins) хранит снапшот приза: правки пула
задним числом не меняют уже выпавшие призы.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from astra.db.base import Base, TimestampMixin
from astra.wheel.enums import SpinType


class WheelPrize(Base, TimestampMixin):
    """Сектор колеса: товар + скидка (100 = бесплатно) + вес выпадения.

    Один товар может присутствовать несколькими строками с разными скидками
    (например «бесплатно» с малым весом и «−50%» с большим).
    """

    __tablename__ = "wheel_prizes"
    __table_args__ = (
        CheckConstraint(
            "discount_percent >= 1 AND discount_percent <= 100",
            name="ck_wheel_prizes_discount_range",
        ),
        CheckConstraint("weight > 0", name="ck_wheel_prizes_weight_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    product_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("products.code", ondelete="CASCADE"),
        index=True,
    )
    discount_percent: Mapped[int] = mapped_column(Integer, default=100)
    weight: Mapped[int] = mapped_column(Integer, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class WheelWin(Base, TimestampMixin):
    """Выигрыш вращения: снапшот приза + жизненный цикл активации.

    Бесплатный выигрыш сгорает в expires_at (конец локального дня пользователя),
    платный живёт до активации (expires_at IS NULL). reading_id — черновик
    расклада, созданный при активации; приз считается использованным только
    когда activated_at проставлен.
    """

    __tablename__ = "wheel_wins"
    __table_args__ = (
        CheckConstraint(
            "discount_percent >= 1 AND discount_percent <= 100",
            name="ck_wheel_wins_discount_range",
        ),
        # Одно бесплатное вращение в локальный день пользователя.
        Index(
            "uq_wheel_wins_free_per_day",
            "user_id",
            "won_on",
            unique=True,
            postgresql_where=text("spin_type = 'free'"),
        ),
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
    prize_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wheel_prizes.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("products.code", ondelete="RESTRICT"),
    )
    discount_percent: Mapped[int] = mapped_column(Integer)
    spin_type: Mapped[str] = mapped_column(String(8), default=SpinType.FREE)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
    )
    reading_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tarot_readings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    won_on: Mapped[date] = mapped_column(Date)  # локальная дата вращения
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
