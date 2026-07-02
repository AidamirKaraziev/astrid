from enum import StrEnum


class PredictionStatus(StrEnum):
    PENDING = "pending"
    CONTEXT_READY = "context_ready"
    TEXT_READY = "text_ready"
    SENT = "sent"
    FAILED = "failed"
