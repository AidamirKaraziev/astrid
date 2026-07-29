"""Что именно считается использованием продукта.

Группы (`UsageKind`) нужны сводкам: в отчёте видно «таро — 140 раз», а внутри
уже разбивка по конкретным раскладам. Конкретное действие (`action`) для
платных продуктов совпадает с `product_code` в каталоге — так метрики
использования и метрики выручки сходятся по одному ключу.
"""

from enum import StrEnum


class UsageKind(StrEnum):
    FORECAST = "forecast"  # карта дня, ежедневный прогноз
    TAROT = "tarot"  # ежедневное таро и платные расклады
    ASK = "ask"  # «Спроси Астрид»
    NATAL = "natal"  # разбор натальной карты
    COMPATIBILITY = "compatibility"  # совместимость
    WHEEL = "wheel"  # колесо фортуны


# Действия без товара в каталоге: бесплатные и пока-бесплатные продукты.
ACTION_DAY_CARD = "day_card"
ACTION_TAROT_DAILY = "tarot_daily"
ACTION_NATAL_REPORT = "natal_report"
ACTION_COMPATIBILITY = "compatibility"
