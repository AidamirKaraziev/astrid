"""Типы вращений колеса фортуны."""

from enum import StrEnum


class SpinType(StrEnum):
    """Бесплатный приз сгорает в конце дня, платный живёт до активации."""

    FREE = "free"
    PAID = "paid"
