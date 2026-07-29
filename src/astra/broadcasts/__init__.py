"""Рассылки: аудитория по фильтрам, ИИ-редактор текста и отправка с подтверждением."""

from astra.broadcasts.audience import Criteria, count, resolve
from astra.broadcasts.editor import Draft, check, improve, personalize_text
from astra.broadcasts.models import (
    Broadcast,
    BroadcastDelivery,
    BroadcastStatus,
    DeliveryStatus,
)

__all__ = [
    "Broadcast",
    "BroadcastDelivery",
    "BroadcastStatus",
    "Criteria",
    "DeliveryStatus",
    "Draft",
    "check",
    "count",
    "improve",
    "personalize_text",
    "resolve",
]
