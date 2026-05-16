"""Import all ORM models for Alembic autogenerate and mapper configuration."""

from astra.points.models import PointsLedger  # noqa: F401
from astra.predictions.models import Prediction  # noqa: F401
from astra.referrals.models import Referral, ReferralCode  # noqa: F401
from astra.users.models import Profile, User  # noqa: F401
