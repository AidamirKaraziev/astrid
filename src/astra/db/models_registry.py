"""Import all ORM models for Alembic autogenerate and mapper configuration."""

from astra.astro.models import NatalChart  # noqa: F401
from astra.compatibility.models import CompatibilityReport, NatalProfile  # noqa: F401
from astra.natal_report.models import NatalReport  # noqa: F401
from astra.places.models import Place  # noqa: F401
from astra.points.models import PointsLedger  # noqa: F401
from astra.predictions.models import Prediction  # noqa: F401
from astra.predictions.zodiac_daily import ZodiacDailyHoroscope  # noqa: F401
from astra.referrals.models import Referral, ReferralCode  # noqa: F401
from astra.tarot.models import TarotDraw, TarotReading  # noqa: F401
from astra.users.models import Profile, User  # noqa: F401
