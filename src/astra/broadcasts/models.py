"""Рассылки: черновик, снимок аудитории и судьба каждого сообщения.

Две таблицы вместо одной, потому что «отправлено 2808» — бесполезное число.
Нужно знать, кому не дошло и почему: у одного бот заблокирован, у другого
сеть отвалилась на середине. Из этих строк собирается и статистика, и кнопка
«повторить недошедшим».

Текст хранится дважды: как его написал человек и как переписала модель. Иначе
после правки промпта невозможно понять, что именно ушло людям.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from astra.db.base import Base, TimestampMixin


class BroadcastStatus(StrEnum):
    DRAFT = "draft"  # собирается в панели
    SENDING = "sending"  # воркер разбирает очередь
    SENT = "sent"  # разослано (возможно, с недошедшими)
    FAILED = "failed"  # не смогли даже начать


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    BLOCKED = "blocked"  # человек заблокировал бота
    FAILED = "failed"  # сеть, лимиты, прочее — можно повторить


class Broadcast(Base, TimestampMixin):
    """Одна рассылка: кому, что и чем закончилось."""

    __tablename__ = "broadcasts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    status: Mapped[str] = mapped_column(String(16), default=BroadcastStatus.DRAFT, index=True)
    # Черновик автора и то, что получилось после модели: сравнивать полезно.
    source_text: Mapped[str] = mapped_column(Text)
    final_text: Mapped[str] = mapped_column(Text)
    used_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    personalize: Mapped[bool] = mapped_column(Boolean, default=False)
    # Условия отбора и кнопки — как их собрали в панели.
    criteria: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    buttons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    image_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Адресная отправка: список telegram_id вместо фильтров.
    direct_recipients: Mapped[list[int]] = mapped_column(JSONB, default=list)

    audience_size: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BroadcastDelivery(Base, TimestampMixin):
    """Судьба одного сообщения: без этого «повторить недошедшим» не сделать."""

    __tablename__ = "broadcast_deliveries"
    __table_args__ = (
        Index("ix_broadcast_deliveries_broadcast_status", "broadcast_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    broadcast_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("broadcasts.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), default=DeliveryStatus.PENDING)
    error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
