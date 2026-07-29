"""Журнал использования: каждое успешное действие человека с продуктом.

Одна строка = один доведённый до конца продукт: карта дня, ежедневное таро,
платный расклад, ответ «Спроси Астрид», натал, совместимость, вращение колеса.
Открытие меню и профиля сюда не попадает — иначе «серия дней» превращается в
«заходил посмотреть».

`local_date` — дата в таймзоне человека, а не сервера. По ней считаются серии,
активность за день и retention: иначе у пользователя восточнее UTC день
переключается вечером и серия рвётся на ровном месте.

Журнал пишется рядом с самим действием и в той же транзакции, поэтому запись
здесь означает, что продукт человек действительно получил.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from astra.db.base import Base, TimestampMixin


class UsageEvent(Base, TimestampMixin):
    """Факт использования продукта: кто, что, платно ли, в какой свой день."""

    __tablename__ = "usage_events"
    __table_args__ = (
        # «Сколько уникальных людей за день» и «была ли активность сегодня».
        Index("ix_usage_events_user_date", "user_id", "local_date"),
        # «Каким продуктом пользуются чаще» за период.
        Index("ix_usage_events_action_created", "action", "created_at"),
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
    # Конкретное действие: day_card, tarot_daily, tarot_wish, ask_love_kids…
    action: Mapped[str] = mapped_column(String(64))
    # Группа для сводок: forecast | tarot | ask | natal | compatibility | wheel
    kind: Mapped[str] = mapped_column(String(24))
    # Платный продукт или бесплатный: разделяет «пользуются» и «покупают».
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    local_date: Mapped[date] = mapped_column(Date, index=True)
