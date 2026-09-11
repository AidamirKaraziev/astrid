"""Внутренний кошелёк в звёздах: леджер начислений, броней и трат.

Настоящие Telegram Stars бот на баланс человека положить не может — в Bot API
такого метода нет. Поэтому награда за приглашённого живёт здесь: свой счёт в
тех же единицах, что и цены каталога (1 запись = 1 ⭐), который списывается при
покупке, а недостающее человек доплачивает обычным инвойсом.

Баланс — сумма `delta` по всем записям. Отдельной колонки с балансом у
пользователя нет намеренно: расхождение суммы и кэша в деньгах обнаруживается
поздно и дорого.

**Бронь.** Между показом инвойса и оплатой баланс нельзя дать потратить
второй раз: иначе человек откроет два инвойса, оба обещают списать одни и те
же 30 ⭐, и оплатив оба получит скидку дважды. Бронь — обычная запись с
отрицательной `delta` и сроком `hold_expires_at`: пока срок не вышел, она
уменьшает баланс. Вышел — перестаёт учитываться сама, без уборщика.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.orm import Mapped, mapped_column

from astra.db.base import Base, TimestampMixin
from astra.db.enums import enum_values


class WalletReason(str, enum.Enum):
    """Откуда взялась запись. HOLD/PURCHASE/RELEASED — стадии одной брони."""

    REFERRAL_REWARD = "referral_reward"
    POINTS_MIGRATION = "points_migration"
    HOLD = "hold"
    PURCHASE = "purchase"
    RELEASED = "released"
    REFUND = "refund"
    MANUAL = "manual"


class StarWalletEntry(Base, TimestampMixin):
    __tablename__ = "star_wallet_entries"

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
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[WalletReason] = mapped_column(
        Enum(WalletReason, name="wallet_reason", values_callable=enum_values),
    )
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Payload инвойса, к которому привязана бронь: по нему хендлер оплаты
    # находит свою бронь, не таская её id через FSM и через Telegram.
    payload: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # Срок брони. NULL — запись постоянная и всегда учитывается в балансе.
    hold_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
