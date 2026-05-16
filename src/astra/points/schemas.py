from pydantic import BaseModel


class PointsBalanceRead(BaseModel):
    points: int
    streak_current: int
    streak_best: int
