"""Учёт обращений к моделям: сколько дёрнули, сколько сожгли, почём.

Пишется из обёртки `TracingLlmProvider` — через неё проходит каждый вызов без
исключения, поэтому счётчик нельзя забыть добавить в новом продукте.

К человеку вызовы намеренно не привязаны: для «сколько стоит нам этот продукт»
достаточно назначения, а тащить user_id через все пайплайны генерации значит
переделать половину сервисов ради строчки в отчёте.

Стоимость считается в момент записи и хранится рядом с токенами. Если считать
её на лету по текущему прайсу, правка цены задним числом перепишет всю
историю — и «себестоимость июля» изменится в августе.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from astra.db.base import Base, TimestampMixin


class LlmCall(Base, TimestampMixin):
    """Один вызов модели: чей продукт, чем считали, чем это обошлось."""

    __tablename__ = "llm_calls"
    __table_args__ = (
        Index("ix_llm_calls_created_purpose", "created_at", "purpose"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Назначение = продукт: tarot_reading, natal, compatibility, ask…
    purpose: Mapped[str] = mapped_column(String(48), index=True)
    status: Mapped[str] = mapped_column(String(16))  # ok | fail
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    # NULL — провайдер не вернул usage. Не выдумываем: лучше дырка, чем ложь.
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    @property
    def total_tokens(self) -> int | None:
        if self.prompt_tokens is None and self.completion_tokens is None:
            return None
        return (self.prompt_tokens or 0) + (self.completion_tokens or 0)


class LlmPrice(Base, TimestampMixin):
    """Прайс модели: сколько стоит миллион токенов входа и выхода.

    Правится из панели: цены меняются чаще, чем выходят релизы, а знать
    себестоимость продукта хочется в тот же день.
    """

    __tablename__ = "llm_prices"
    __table_args__ = (
        CheckConstraint("input_per_million >= 0", name="ck_llm_prices_input_positive"),
        CheckConstraint("output_per_million >= 0", name="ck_llm_prices_output_positive"),
    )

    model: Mapped[str] = mapped_column(String(64), primary_key=True)
    input_per_million: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    output_per_million: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    note: Mapped[str | None] = mapped_column(String(128), nullable=True)

    def cost_usd(self, prompt_tokens: int | None, completion_tokens: int | None) -> Decimal | None:
        """Стоимость вызова; None — токенов нет, считать не из чего."""
        if prompt_tokens is None and completion_tokens is None:
            return None
        million = Decimal(1_000_000)
        incoming = Decimal(prompt_tokens or 0) * self.input_per_million / million
        outgoing = Decimal(completion_tokens or 0) * self.output_per_million / million
        return (incoming + outgoing).quantize(Decimal("0.000001"))
