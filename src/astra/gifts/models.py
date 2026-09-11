"""Подарок: разбор, который один человек дарит другому за счёт бота.

Даритель выбирает продукт из каталога и получает ссылку `?start=gift_<код>`.
Ссылку он отправляет кому угодно; активировать её может только человек, которого
в боте ещё нет, и только один раз от этого дарителя.

Почему «только новому»: подарок — канал роста, а не скидка постоянным
пользователям. Почему «один на пару»: иначе один человек раздаёт себе же
бесконечную ленту подарков через новые аккаунты.

Подарок несёт и реферальную привязку: отдельную ссылку «пригласить» дарителю
для этого слать не нужно.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from astra.db.base import Base, TimestampMixin
from astra.db.enums import enum_values


class GiftStatus(str, enum.Enum):
    ISSUED = "issued"
    REDEEMED = "redeemed"
    REVOKED = "revoked"


class Gift(Base, TimestampMixin):
    __tablename__ = "gifts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    giver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    # Код в ссылке. Короткий и без похожих символов: его читают с чужого экрана.
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    product_code: Mapped[str] = mapped_column(String(64))
    status: Mapped[GiftStatus] = mapped_column(
        Enum(GiftStatus, name="gift_status", values_callable=enum_values),
        default=GiftStatus.ISSUED,
        index=True,
    )
    redeemed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
