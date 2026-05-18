import enum
from typing import TypeVar

E = TypeVar("E", bound=enum.Enum)


def enum_values(enum_class: type[E]) -> list[str]:
    """SQLAlchemy values_callable: store enum .value, not .name (PostgreSQL)."""
    return [member.value for member in enum_class]
