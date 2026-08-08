"""Как внутренний баланс участвует в покупке: бронь → инвойс на остаток → списание.

Один вход для всех платных продуктов. Хендлер спрашивает `plan_charge`, получает
разбивку «столько-то со счёта, столько-то инвойсом» и дальше ведёт себя как
раньше — просто с другой суммой в инвойсе.

Три исхода покупки, и каждый обязан быть обработан:

* оплата прошла → `settle_charge`, бронь становится списанием;
* человек передумал или платёж отвалился → `cancel_charge`, звёзды вернулись;
* никто ничего не сделал → бронь протухнет сама, звёзды вернутся через час.

Инвойс на 0 ⭐ Telegram не принимает, поэтому когда баланс покрывает всю цену,
инвойса нет вовсе — продукт выдаётся сразу, как по стопроцентной скидке.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.observability import Event, get_logger
from astra.payments.service import ProductPriceInfo
from astra.wallet import crud as wallet_crud
from astra.wallet.models import WalletReason

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Charge:
    """Как разложилась цена между внутренним счётом и инвойсом."""

    price: ProductPriceInfo
    from_wallet: int
    to_invoice: int

    @property
    def covered_by_wallet(self) -> bool:
        """Инвойс не нужен: цена закрыта балансом (или товар и так бесплатный)."""
        return self.to_invoice == 0


async def plan_charge(
    session: AsyncSession,
    user_id: UUID,
    price: ProductPriceInfo,
    *,
    payload: str,
    description: str | None = None,
) -> Charge:
    """Разложить цену и забронировать внутреннюю часть под этот payload."""
    if price.is_free:
        return Charge(price, from_wallet=0, to_invoice=0)

    balance = await wallet_crud.get_balance(session, user_id)
    from_wallet = min(max(balance, 0), price.final_amount)
    if from_wallet <= 0:
        return Charge(price, from_wallet=0, to_invoice=price.final_amount)

    await wallet_crud.hold(
        session,
        user_id,
        from_wallet,
        payload=payload,
        description=description,
    )
    log.info(
        Event.WALLET_HOLD_CREATED,
        user_id=user_id,
        payload=payload,
        amount=from_wallet,
        balance=balance,
    )
    return Charge(price, from_wallet=from_wallet, to_invoice=price.final_amount - from_wallet)


async def settle_charge(
    session: AsyncSession,
    user_id: UUID,
    payload: str,
    *,
    description: str | None = None,
) -> int:
    """Оплата прошла: закрепить списание. Возвращает сколько ушло со счёта.

    Если бронь успела протухнуть (человек оплатил инвойс через час), списываем
    столько, сколько есть на счету сейчас: уйти в минус кошелёк не должен.
    """
    entry = await wallet_crud.find_hold(session, user_id, payload)
    if entry is None:
        return 0

    promised = -entry.delta
    expired = entry.hold_expires_at is not None and entry.hold_expires_at <= datetime.now(UTC)
    if not expired:
        await wallet_crud.settle_hold(session, entry, description=description)
        log.info(Event.WALLET_SPENT, user_id=user_id, payload=payload, amount=promised)
        return promised

    await wallet_crud.release_hold(session, entry)
    balance = await wallet_crud.get_balance(session, user_id)
    amount = min(promised, max(balance, 0))
    if amount <= 0:
        log.info(Event.WALLET_HOLD_EXPIRED, user_id=user_id, payload=payload, promised=promised)
        return 0
    await wallet_crud.add_entry(
        session,
        user_id,
        -amount,
        WalletReason.PURCHASE,
        description=description,
        payload=payload,
    )
    log.info(Event.WALLET_SPENT, user_id=user_id, payload=payload, amount=amount, late=True)
    return amount


async def cancel_charge(session: AsyncSession, user_id: UUID, payload: str) -> int:
    """Покупка не состоялась: снять бронь. Возвращает сколько вернулось."""
    entry = await wallet_crud.find_hold(session, user_id, payload)
    if entry is None:
        return 0
    await wallet_crud.release_hold(session, entry)
    amount = -entry.delta
    log.info(Event.WALLET_HOLD_RELEASED, user_id=user_id, payload=payload, amount=amount)
    return amount


async def refund_to_wallet(
    session: AsyncSession,
    user_id: UUID,
    payload: str,
    *,
    description: str | None = None,
) -> int:
    """Вернуть на счёт то, что было списано по этому payload.

    Нужен, когда продукт не состоялся уже после оплаты: звёзды Telegram
    возвращает своим refund, а внутреннюю часть возвращаем мы.
    """
    entry = await wallet_crud.find_by_payload(
        session,
        user_id,
        payload,
        WalletReason.PURCHASE,
    )
    if entry is None:
        return 0
    amount = -entry.delta
    await wallet_crud.add_entry(
        session,
        user_id,
        amount,
        WalletReason.REFUND,
        description=description,
        payload=payload,
    )
    log.info(Event.WALLET_REFUNDED, user_id=user_id, payload=payload, amount=amount)
    return amount
