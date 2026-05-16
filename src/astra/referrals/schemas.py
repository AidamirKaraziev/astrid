from pydantic import BaseModel


class ReferralStatsRead(BaseModel):
    code: str
    referral_link: str
    invited_count: int
    points_earned: int
