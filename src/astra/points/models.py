import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from astra.db.base import Base, TimestampMixin
from astra.db.enums import enum_values


class PointsReason(str, enum.Enum):
    DAILY_VISIT = "daily_visit"
    REFERRAL_BONUS = "referral_bonus"
    REFERRAL_WELCOME = "referral_welcome"
    MANUAL = "manual"


class PointsLedger(Base, TimestampMixin):
    __tablename__ = "points_ledger"

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
    reason: Mapped[PointsReason] = mapped_column(
        Enum(PointsReason, name="points_reason", values_callable=enum_values),
    )
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
