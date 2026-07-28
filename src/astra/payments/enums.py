"""Статусы платежей, провайдеры и виды товаров."""

from enum import StrEnum


class PaymentStatus(StrEnum):
    COMPLETED = "completed"
    REFUNDED = "refunded"


class PaymentProvider(StrEnum):
    TELEGRAM_STARS = "telegram_stars"
    # Этап 2: карточный провайдер (внешняя платёжная страница) добавится сюда.


class ProductKind(StrEnum):
    TAROT_READING = "tarot_reading"
    ASK_ANSWER = "ask_answer"  # ответ на вопрос в разделе «Спроси Астрид»


CURRENCY_XTR = "XTR"  # Telegram Stars
