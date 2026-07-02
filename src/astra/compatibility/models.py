import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from astra.compatibility.enums import PairMode, RelationshipContext, ReportStatus
from astra.db.base import Base, TimestampMixin
from astra.users.gender import Gender


class NatalProfile(Base, TimestampMixin):
    """Натальная карточка человека (партнёр, знакомый) — владелец Telegram-аккаунта."""

    __tablename__ = "natal_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    label: Mapped[str] = mapped_column(String(255), index=True)
    gender: Mapped[Gender | None] = mapped_column(String(16), nullable=True)
    birth_date: Mapped[date] = mapped_column(Date)
    birth_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    birth_place: Mapped[str] = mapped_column(String(255))
    birth_place_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("places.id", ondelete="SET NULL"),
        nullable=True,
    )
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    chart_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    owner: Mapped["User"] = relationship(back_populates="natal_profiles")  # noqa: F821


class CompatibilityReport(Base, TimestampMixin):
    __tablename__ = "compatibility_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    relationship_context: Mapped[str] = mapped_column(String(32))
    pair_mode: Mapped[str] = mapped_column(String(32))
    person_a_natal_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("natal_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    person_b_natal_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("natal_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    person_a_snapshot: Mapped[dict] = mapped_column(JSONB)
    person_b_snapshot: Mapped[dict] = mapped_column(JSONB)
    llm_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    astro_context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default=ReportStatus.PENDING)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped["User"] = relationship(back_populates="compatibility_reports")  # noqa: F821
