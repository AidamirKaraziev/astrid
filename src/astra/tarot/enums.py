"""Статусы платного расклада — жизненный цикл как у ReportStatus совместимости."""

from enum import StrEnum


class ReadingStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"  # черновик: вопрос принят, ждём оплату Stars
    PENDING = "pending"
    GENERATING = "generating"
    TEXT_READY = "text_ready"
    READY = "ready"
    FAILED = "failed"


READING_IN_FLIGHT_STATUSES: frozenset[ReadingStatus] = frozenset(
    {ReadingStatus.GENERATING, ReadingStatus.TEXT_READY},
)
