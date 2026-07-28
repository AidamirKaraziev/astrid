"""Статусы ответа в разделе «Спроси Астрид»."""

from enum import StrEnum


class AskStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"  # черновик: вопрос выбран, ждём оплату
    GENERATING = "generating"  # оплачен, числа посчитаны, ждём разбор от LLM
    READY = "ready"
    FAILED = "failed"  # разбор не собрался, звёзды возвращены
