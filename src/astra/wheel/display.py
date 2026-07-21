"""Человеческие подписи призов: эмодзи, название товара, размер скидки."""

from __future__ import annotations

from astra.tarot.spreads import SPREADS, SpreadType

_TAROT_PREFIX = "tarot_"
_FALLBACK_EMOJI = "🎁"


def product_display(product_code: str) -> tuple[str, str]:
    """(эмодзи, название) товара; для незнакомого кода — подарок и сам код."""
    if product_code.startswith(_TAROT_PREFIX):
        try:
            spec = SPREADS[SpreadType(product_code.removeprefix(_TAROT_PREFIX))]
        except (ValueError, KeyError):
            return _FALLBACK_EMOJI, product_code
        return spec.emoji, spec.title_ru
    return _FALLBACK_EMOJI, product_code


def discount_label(discount_percent: int) -> str:
    return "бесплатно" if discount_percent >= 100 else f"−{discount_percent}%"


def prize_label(product_code: str, discount_percent: int) -> str:
    emoji, title = product_display(product_code)
    return f"{emoji} {title} · {discount_label(discount_percent)}"
