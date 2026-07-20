"""Оплата раскладов таро в Telegram Stars.

Жизненный цикл: черновик расклада (pending_payment) → инвойс XTR →
successful_payment → расклад оплачен и уходит в пайплайн генерации.
При финальном фейле генерации worker возвращает звёзды (refundStarPayment).

Цены — в каталоге products/product_prices (товар × валюта); платёж хранит
снапшот цены и скидки на момент оплаты.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger
from astra.payments import models as payments_crud
from astra.payments.enums import CURRENCY_XTR, PaymentProvider
from astra.payments.models import Payment
from astra.tarot.models import TarotReading
from astra.users.models import User

log = get_logger(__name__)

_TAROT_PAYLOAD_PREFIX = "tarot:"


def tarot_product_code(spread_type: str) -> str:
    return f"tarot_{spread_type}"


def tarot_invoice_payload(reading_id: UUID) -> str:
    return f"{_TAROT_PAYLOAD_PREFIX}{reading_id}"


def parse_tarot_invoice_payload(payload: str | None) -> UUID | None:
    """UUID черновика расклада из payload инвойса; None — чужой/битый payload."""
    if not payload or not payload.startswith(_TAROT_PAYLOAD_PREFIX):
        return None
    try:
        return UUID(payload.removeprefix(_TAROT_PAYLOAD_PREFIX))
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class ProductPriceInfo:
    """Цена товара в валюте с учётом акции: base — «старая» цена, final — к оплате.

    Суммы — в минорных единицах валюты (Stars: 1 ⭐, RUB: копейки).
    """

    currency: str
    base_amount: int
    discount_percent: int = 0

    @property
    def has_discount(self) -> bool:
        return 0 < self.discount_percent < 100

    @property
    def final_amount(self) -> int:
        if not self.has_discount:
            return self.base_amount
        # Округляем до минорной единицы; акция не может обнулить цену — минимум 1.
        return max(1, round(self.base_amount * (100 - self.discount_percent) / 100))


async def get_tarot_price(
    session: AsyncSession,
    spread_type: str,
    currency: str = CURRENCY_XTR,
) -> ProductPriceInfo:
    """Цена расклада из каталога; для XTR есть фолбэк на конфиг, если строки нет."""
    row = await payments_crud.get_product_price(
        session,
        tarot_product_code(spread_type),
        currency,
    )
    if row is not None:
        return ProductPriceInfo(row.currency, row.amount, row.discount_percent)
    if currency == CURRENCY_XTR:
        return ProductPriceInfo(CURRENCY_XTR, get_settings().tarot_reading_price_stars)
    raise ValueError(f"нет цены {currency} для {tarot_product_code(spread_type)}")


async def register_tarot_payment(
    session: AsyncSession,
    *,
    user: User,
    reading: TarotReading,
    provider_charge_id: str,
    amount: int,
    currency: str,
) -> Payment | None:
    """Записать успешный платёж Stars; None — этот charge_id уже обработан (дубль).

    Снапшот base/discount берём из каталога, если он сходится с фактически
    уплаченной суммой; если цена успела измениться между инвойсом и оплатой —
    фиксируем факт: base = amount, скидка 0.
    """
    provider = PaymentProvider.TELEGRAM_STARS
    existing = await payments_crud.get_payment_by_charge(session, provider, provider_charge_id)
    if existing is not None:
        log.warning(
            Event.PAYMENT_DUPLICATE,
            user_id=user.id,
            reading_id=reading.id,
            charge_id=provider_charge_id,
        )
        return None

    product_code = tarot_product_code(reading.spread_type)
    try:
        price = await get_tarot_price(session, reading.spread_type, currency)
    except ValueError:
        price = None
    if price is not None and price.final_amount == amount:
        base_amount, discount_percent = price.base_amount, price.discount_percent
    else:
        base_amount, discount_percent = amount, 0

    payment = await payments_crud.create_payment(
        session,
        user_id=user.id,
        product_code=product_code,
        reading_id=reading.id,
        currency=currency,
        amount=amount,
        base_amount=base_amount,
        discount_percent=discount_percent,
        provider=provider,
        provider_charge_id=provider_charge_id,
    )
    log.info(
        Event.PAYMENT_COMPLETED,
        user_id=user.id,
        reading_id=reading.id,
        payment_id=payment.id,
        amount=amount,
        currency=currency,
        discount_percent=discount_percent,
    )
    return payment


async def refund_star_payment_api(
    telegram_id: int,
    provider_charge_id: str,
    settings: Settings | None = None,
) -> None:
    """Прямой вызов Bot API refundStarPayment (для worker, без aiogram Bot)."""
    cfg = settings or get_settings()
    if not cfg.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    url = f"https://api.telegram.org/bot{cfg.telegram_bot_token}/refundStarPayment"
    client_kwargs: dict[str, Any] = {"timeout": 30.0}
    if proxy := cfg.telegram_proxy_url_effective:
        client_kwargs["proxy"] = proxy
    async with httpx.AsyncClient(**client_kwargs) as client:
        response = await client.post(
            url,
            json={
                "user_id": telegram_id,
                "telegram_payment_charge_id": provider_charge_id,
            },
        )
        response.raise_for_status()


async def refund_reading_payment(
    session: AsyncSession,
    reading: TarotReading,
    telegram_id: int,
    settings: Settings | None = None,
) -> bool:
    """Вернуть звёзды за расклад; True — refund прошёл (или платежа не было — False).

    Идемпотентно: уже возвращённый платёж повторно не трогаем.
    """
    payment = await payments_crud.get_completed_payment_for_reading(session, reading.id)
    if payment is None:
        return False
    try:
        await refund_star_payment_api(
            telegram_id,
            payment.provider_charge_id,
            settings,
        )
    except Exception as exc:
        # Платёж остаётся completed — можно вернуть вручную по charge_id из лога.
        log.error(
            Event.PAYMENT_REFUND_FAILED,
            payment_id=payment.id,
            reading_id=reading.id,
            charge_id=payment.provider_charge_id,
            error_type=type(exc).__name__,
        )
        return False
    await payments_crud.mark_payment_refunded(session, payment)
    log.info(
        Event.PAYMENT_REFUNDED,
        payment_id=payment.id,
        reading_id=reading.id,
        amount=payment.amount,
    )
    return True
