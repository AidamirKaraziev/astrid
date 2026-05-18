import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from astra.db.base import Base, TimestampMixin
from astra.db.enums import enum_values


class ReferralStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    REWARDED = "rewarded"


class ReferralCode(Base, TimestampMixin):
    __tablename__ = "referral_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
    )
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    user: Mapped["User"] = relationship(back_populates="referral_code")


class Referral(Base, TimestampMixin):
    __tablename__ = "referrals"
    __table_args__ = (UniqueConstraint("invitee_id", name="uq_referrals_invitee"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    referrer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    invitee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    status: Mapped[ReferralStatus] = mapped_column(
        Enum(ReferralStatus, name="referral_status", values_callable=enum_values),
        default=ReferralStatus.PENDING,
    )
    rewarded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
