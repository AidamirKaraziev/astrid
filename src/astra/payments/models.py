"""Каталог товаров, мультивалютные цены и платежи.

Деньги — только целые в минорных единицах валюты (Stars: 1 ⭐, RUB: копейки).
Новая валюта = новая строка в product_prices, схема не меняется.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from astra.db.base import Base, TimestampMixin
from astra.payments.enums import PaymentProvider, PaymentStatus


class Product(Base, TimestampMixin):
    """Справочник товаров: code — стабильный идентификатор (tarot_wish и т.п.)."""

    __tablename__ = "products"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProductPrice(Base, TimestampMixin):
    """Цена товара в конкретной валюте + текущая скидка на него."""

    __tablename__ = "product_prices"
    __table_args__ = (
        UniqueConstraint("product_code", "currency", name="uq_product_prices_product_currency"),
        CheckConstraint("amount > 0", name="ck_product_prices_amount_positive"),
        CheckConstraint(
            "discount_percent >= 0 AND discount_percent <= 99",
            name="ck_product_prices_discount_range",
        ),
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
    currency: Mapped[str] = mapped_column(String(8))
    amount: Mapped[int] = mapped_column(Integer)  # минорные единицы валюты
    discount_percent: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Payment(Base, TimestampMixin):
    """Факт оплаты — самодостаточный финансовый документ.

    base_amount/discount_percent — снапшот цены в момент оплаты: будущие правки
    каталога не искажают отчётность.
    """

    __tablename__ = "payments"
    __table_args__ = (
        # Идемпотентность: Telegram может прислать successful_payment повторно.
        UniqueConstraint("provider", "provider_charge_id", name="uq_payments_provider_charge"),
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        CheckConstraint(
            "discount_percent >= 0 AND discount_percent <= 99",
            name="ck_payments_discount_range",
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
    product_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("products.code", ondelete="RESTRICT"),
    )
    reading_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tarot_readings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(8))
    amount: Mapped[int] = mapped_column(Integer)  # фактически уплачено (минорные единицы)
    base_amount: Mapped[int] = mapped_column(Integer)  # цена без скидки на момент оплаты
    discount_percent: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str] = mapped_column(String(32), default=PaymentProvider.TELEGRAM_STARS)
    provider_charge_id: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default=PaymentStatus.COMPLETED)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


async def get_product_price(
    session: AsyncSession,
    product_code: str,
    currency: str,
) -> ProductPrice | None:
    result = await session.execute(
        select(ProductPrice).where(
            ProductPrice.product_code == product_code,
            ProductPrice.currency == currency,
            ProductPrice.is_active.is_(True),
        ),
    )
    return result.scalar_one_or_none()


async def get_payment_by_charge(
    session: AsyncSession,
    provider: str,
    provider_charge_id: str,
) -> Payment | None:
    result = await session.execute(
        select(Payment).where(
            Payment.provider == provider,
            Payment.provider_charge_id == provider_charge_id,
        ),
    )
    return result.scalar_one_or_none()


async def get_completed_payment_for_reading(
    session: AsyncSession,
    reading_id: uuid.UUID,
) -> Payment | None:
    result = await session.execute(
        select(Payment).where(
            Payment.reading_id == reading_id,
            Payment.status == PaymentStatus.COMPLETED,
        ),
    )
    return result.scalar_one_or_none()


async def create_payment(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    product_code: str,
    reading_id: uuid.UUID | None,
    currency: str,
    amount: int,
    base_amount: int,
    discount_percent: int,
    provider: str,
    provider_charge_id: str,
) -> Payment:
    row = Payment(
        user_id=user_id,
        product_code=product_code,
        reading_id=reading_id,
        currency=currency,
        amount=amount,
        base_amount=base_amount,
        discount_percent=discount_percent,
        provider=provider,
        provider_charge_id=provider_charge_id,
        status=PaymentStatus.COMPLETED,
    )
    session.add(row)
    await session.flush()
    return row


async def mark_payment_refunded(session: AsyncSession, payment: Payment) -> None:
    payment.status = PaymentStatus.REFUNDED
    payment.refunded_at = datetime.now(UTC)
    await session.flush()
