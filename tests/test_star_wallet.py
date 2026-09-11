"""Внутренний кошелёк: баланс, бронь под инвойс, списание и возврат.

Тесты идут на живой базе, а не на моках: вся суть кошелька — арифметика по
леджеру и срок брони, то есть ровно то, что мок подтвердит не проверив.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from astra.payments.service import ProductPriceInfo
from astra.services.wallet_service import (
    cancel_charge,
    plan_charge,
    refund_to_wallet,
    settle_charge,
)
from astra.wallet import crud as wallet_crud
from astra.wallet.models import WalletReason

from conftest import new_test_telegram_id

pytestmark = pytest.mark.asyncio

PRICE_50 = ProductPriceInfo("XTR", 50)
FREE = ProductPriceInfo("XTR", 50, 100)


async def _user(session):
    from astra.users import crud as users_crud

    user = await users_crud.create_user(
        session,
        telegram_id=new_test_telegram_id(),
        username=None,
        language_code="ru",
    )
    await session.flush()
    return user


async def _credit(session, user, amount: int) -> None:
    await wallet_crud.add_entry(
        session,
        user.id,
        amount,
        WalletReason.REFERRAL_REWARD,
        description="тест",
    )


class TestBalance:
    async def test_starts_empty(self, db_session) -> None:
        user = await _user(db_session)
        assert await wallet_crud.get_balance(db_session, user.id) == 0

    async def test_sums_entries(self, db_session) -> None:
        user = await _user(db_session)
        await _credit(db_session, user, 10)
        await _credit(db_session, user, 10)
        assert await wallet_crud.get_balance(db_session, user.id) == 20

    async def test_expired_hold_returns_to_balance_on_its_own(self, db_session) -> None:
        """Никакого уборщика в фоне: просроченная бронь просто перестаёт считаться."""
        user = await _user(db_session)
        await _credit(db_session, user, 30)
        entry = await wallet_crud.hold(db_session, user.id, 30, payload="p:1")
        assert await wallet_crud.get_balance(db_session, user.id) == 0

        entry.hold_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db_session.flush()
        assert await wallet_crud.get_balance(db_session, user.id) == 30


class TestPlanCharge:
    async def test_empty_wallet_sends_full_price_to_invoice(self, db_session) -> None:
        user = await _user(db_session)
        charge = await plan_charge(db_session, user.id, PRICE_50, payload="p:1")
        assert (charge.from_wallet, charge.to_invoice) == (0, 50)
        assert not charge.covered_by_wallet

    async def test_partial_balance_splits_the_price(self, db_session) -> None:
        user = await _user(db_session)
        await _credit(db_session, user, 30)

        charge = await plan_charge(db_session, user.id, PRICE_50, payload="p:1")

        assert (charge.from_wallet, charge.to_invoice) == (30, 20)
        # Забронированное сразу вычтено: второй инвойс не пообещает те же 30.
        assert await wallet_crud.get_balance(db_session, user.id) == 0

    async def test_full_balance_needs_no_invoice(self, db_session) -> None:
        user = await _user(db_session)
        await _credit(db_session, user, 70)

        charge = await plan_charge(db_session, user.id, PRICE_50, payload="p:1")

        assert (charge.from_wallet, charge.to_invoice) == (50, 0)
        assert charge.covered_by_wallet

    async def test_free_product_touches_nothing(self, db_session) -> None:
        user = await _user(db_session)
        await _credit(db_session, user, 30)

        charge = await plan_charge(db_session, user.id, FREE, payload="p:1")

        assert charge.covered_by_wallet
        assert charge.from_wallet == 0
        assert await wallet_crud.get_balance(db_session, user.id) == 30

    async def test_two_invoices_cannot_promise_the_same_stars(self, db_session) -> None:
        """Ради этого и нужна бронь: иначе скидку получили бы дважды."""
        user = await _user(db_session)
        await _credit(db_session, user, 30)

        first = await plan_charge(db_session, user.id, PRICE_50, payload="p:1")
        second = await plan_charge(db_session, user.id, PRICE_50, payload="p:2")

        assert first.from_wallet == 30
        assert second.from_wallet == 0
        assert second.to_invoice == 50


class TestSettleAndCancel:
    async def test_payment_makes_the_hold_permanent(self, db_session) -> None:
        user = await _user(db_session)
        await _credit(db_session, user, 30)
        await plan_charge(db_session, user.id, PRICE_50, payload="p:1")

        spent = await settle_charge(db_session, user.id, "p:1", description="Три карты")

        assert spent == 30
        assert await wallet_crud.get_balance(db_session, user.id) == 0
        entry = await wallet_crud.find_by_payload(
            db_session, user.id, "p:1", WalletReason.PURCHASE,
        )
        assert entry is not None and entry.hold_expires_at is None

    async def test_cancel_returns_stars_at_once(self, db_session) -> None:
        user = await _user(db_session)
        await _credit(db_session, user, 30)
        await plan_charge(db_session, user.id, PRICE_50, payload="p:1")

        returned = await cancel_charge(db_session, user.id, "p:1")

        assert returned == 30
        assert await wallet_crud.get_balance(db_session, user.id) == 30

    async def test_nothing_to_settle_without_a_hold(self, db_session) -> None:
        user = await _user(db_session)
        assert await settle_charge(db_session, user.id, "p:1") == 0

    async def test_late_payment_never_overdraws(self, db_session) -> None:
        """Человек вернулся к старому инвойсу через час: списываем не больше, чем есть."""
        user = await _user(db_session)
        await _credit(db_session, user, 30)
        entry = await wallet_crud.hold(db_session, user.id, 30, payload="p:1")
        entry.hold_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db_session.flush()
        # Пока бронь протухала, звёзды ушли на другую покупку.
        await wallet_crud.add_entry(db_session, user.id, -20, WalletReason.PURCHASE)

        spent = await settle_charge(db_session, user.id, "p:1")

        assert spent == 10  # на счету было ровно столько
        assert await wallet_crud.get_balance(db_session, user.id) == 0

    async def test_refund_returns_spent_stars(self, db_session) -> None:
        user = await _user(db_session)
        await _credit(db_session, user, 30)
        await plan_charge(db_session, user.id, PRICE_50, payload="p:1")
        await settle_charge(db_session, user.id, "p:1")

        returned = await refund_to_wallet(db_session, user.id, "p:1")

        assert returned == 30
        assert await wallet_crud.get_balance(db_session, user.id) == 30

    async def test_refund_without_purchase_is_noop(self, db_session) -> None:
        user = await _user(db_session)
        await _credit(db_session, user, 30)
        await plan_charge(db_session, user.id, PRICE_50, payload="p:1")

        assert await refund_to_wallet(db_session, user.id, "p:1") == 0
