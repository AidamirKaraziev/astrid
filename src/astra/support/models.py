"""Тикеты службы заботы: связь «сообщение в админ-группе → клиент».

Оператор отвечает reply на карточку обращения в группе; бот по
`admin_message_id` находит тикет и доставляет ответ клиенту в бот.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from astra.db.base import Base, TimestampMixin


class SupportTicket(Base, TimestampMixin):
    __tablename__ = "support_tickets"
    __table_args__ = (
        # Ответ оператора ищем по (чат группы, id карточки) — пара уникальна.
        UniqueConstraint(
            "admin_chat_id",
            "admin_message_id",
            name="uq_support_tickets_admin_message",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    # Человеко-понятный номер обращения (#1000, #1001, …).
    number: Mapped[int] = mapped_column(BigInteger, Identity(start=1000), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    # Денормализованный telegram_id — чтобы доставить ответ без лишнего JOIN.
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    admin_chat_id: Mapped[int] = mapped_column(BigInteger)
    admin_message_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default="open")
    last_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
