"""Сбой таро и «Спроси»: возвращается и часть со счёта, и платёж Telegram.

Живая база, настоящие модели; мокается только Telegram API.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from astra.ask import models as ask_crud
from astra.payments import models as payments_crud
from astra.payments.enums import CURRENCY_XTR, PaymentProvider
from astra.payments.models import Product
from astra.payments.service import (
    ask_invoice_payload,
    refund_reading_payment,
    tarot_invoice_payload,
)
from astra.services.ask_service import refund_ask_payment
from astra.services.wallet_service import refund_to_wallet
from astra.tarot import models as tarot_crud
from astra.users import crud as users_crud
from astra.wallet import crud as wallet_crud
from astra.wallet.models import WalletReason

from conftest import new_test_telegram_id

pytestmark = pytest.mark.asyncio

API = "astra.payments.service.refund_star_payment_api"
PRODUCT = "tarot_refund_test"


async def _user(session):
    user = await users_crud.create_user(
        session,
        telegram_id=new_test_telegram_id(),
        username=None,
        language_code="ru",
    )
    await session.flush()
    return user


async def _spent_from_wallet(session, user, payload: str, amount: int) -> None:
    """Списание со счёта, как после settle_charge: PURCHASE по payload."""
    await wallet_crud.add_entry(
        session, user.id, amount, WalletReason.REFERRAL_REWARD, description="тест"
    )
    await wallet_crud.add_entry(
        session, user.id, -amount, WalletReason.PURCHASE, payload=payload, description="тест"
    )


async def _balance(session, user) -> int:
    return await wallet_crud.get_balance(session, user.id)


async def _tarot(session, user, *, invoice: bool, wallet: int):
    reading = await tarot_crud.create_reading(
        session, user_id=user.id, target=date.today(), spread_type="three", question=None, cards=[]
    )
    if invoice:
        if await session.get(Product, PRODUCT) is None:
            session.add(Product(code=PRODUCT, kind="tarot", title="Тест"))
            await session.flush()
        await payments_crud.create_payment(
            session,
            user_id=user.id,
            product_code=PRODUCT,
            reading_id=reading.id,
            currency=CURRENCY_XTR,
            amount=30,
            base_amount=30,
            discount_percent=0,
            provider=PaymentProvider.TELEGRAM_STARS,
            provider_charge_id=f"ch-{uuid.uuid4()}",
        )
    if wallet:
        await _spent_from_wallet(session, user, tarot_invoice_payload(reading.id), wallet)
    return reading


async def _ask(session, user, *, invoice: bool, wallet: int):
    reading = await ask_crud.create_draft(
        session, user_id=user.id, question_key="q_refund_test", in_relationship=None
    )
    await ask_crud.mark_paid(
        session,
        reading,
        amount=30,
        charge_id=f"ch-{uuid.uuid4()}" if invoice else None,
        computed={},
        methodology_version=1,
    )
    if wallet:
        await _spent_from_wallet(session, user, ask_invoice_payload(reading.id), wallet)
    return reading


class TestRefundToWalletIdempotent:
    async def test_second_call_credits_nothing(self, db_session) -> None:
        user = await _user(db_session)
        await _spent_from_wallet(db_session, user, "p:1", 20)
        assert await refund_to_wallet(db_session, user.id, "p:1") == 20
        assert await refund_to_wallet(db_session, user.id, "p:1") == 0
        assert await _balance(db_session, user) == 20


class TestTarot:
    async def test_invoice_only(self, db_session) -> None:
        user = await _user(db_session)
        reading = await _tarot(db_session, user, invoice=True, wallet=0)
        with patch(API, new=AsyncMock()) as api:
            assert await refund_reading_payment(db_session, reading, user.telegram_id) is True
        api.assert_awaited_once()

    async def test_invoice_and_wallet(self, db_session) -> None:
        user = await _user(db_session)
        reading = await _tarot(db_session, user, invoice=True, wallet=20)
        with patch(API, new=AsyncMock()) as api:
            assert await refund_reading_payment(db_session, reading, user.telegram_id) is True
        api.assert_awaited_once()
        assert await _balance(db_session, user) == 20

    async def test_wallet_only(self, db_session) -> None:
        user = await _user(db_session)
        reading = await _tarot(db_session, user, invoice=False, wallet=20)
        with patch(API, new=AsyncMock()) as api:
            assert await refund_reading_payment(db_session, reading, user.telegram_id) is True
        api.assert_not_awaited()
        assert await _balance(db_session, user) == 20

    async def test_telegram_fails_wallet_still_returned(self, db_session) -> None:
        user = await _user(db_session)
        reading = await _tarot(db_session, user, invoice=True, wallet=20)
        with patch(API, new=AsyncMock(side_effect=RuntimeError("boom"))):
            assert await refund_reading_payment(db_session, reading, user.telegram_id) is False
        assert await _balance(db_session, user) == 20

    async def test_repeat_credits_nothing(self, db_session) -> None:
        user = await _user(db_session)
        reading = await _tarot(db_session, user, invoice=True, wallet=20)
        with patch(API, new=AsyncMock()) as api:
            assert await refund_reading_payment(db_session, reading, user.telegram_id) is True
            assert await refund_reading_payment(db_session, reading, user.telegram_id) is False
        api.assert_awaited_once()
        assert await _balance(db_session, user) == 20

    async def test_free_returns_false(self, db_session) -> None:
        user = await _user(db_session)
        reading = await _tarot(db_session, user, invoice=False, wallet=0)
        assert await refund_reading_payment(db_session, reading, user.telegram_id) is False


class TestAsk:
    async def test_invoice_only(self, db_session) -> None:
        user = await _user(db_session)
        reading = await _ask(db_session, user, invoice=True, wallet=0)
        with patch(API, new=AsyncMock()) as api:
            assert await refund_ask_payment(db_session, reading, user.telegram_id) is True
        api.assert_awaited_once()
        assert reading.refunded is True

    async def test_invoice_and_wallet(self, db_session) -> None:
        user = await _user(db_session)
        reading = await _ask(db_session, user, invoice=True, wallet=20)
        with patch(API, new=AsyncMock()) as api:
            assert await refund_ask_payment(db_session, reading, user.telegram_id) is True
        api.assert_awaited_once()
        assert await _balance(db_session, user) == 20

    async def test_wallet_only(self, db_session) -> None:
        user = await _user(db_session)
        reading = await _ask(db_session, user, invoice=False, wallet=20)
        with patch(API, new=AsyncMock()) as api:
            assert await refund_ask_payment(db_session, reading, user.telegram_id) is True
        api.assert_not_awaited()
        assert await _balance(db_session, user) == 20

    async def test_telegram_fails_wallet_still_returned(self, db_session) -> None:
        user = await _user(db_session)
        reading = await _ask(db_session, user, invoice=True, wallet=20)
        with patch(API, new=AsyncMock(side_effect=RuntimeError("boom"))):
            assert await refund_ask_payment(db_session, reading, user.telegram_id) is False
        assert await _balance(db_session, user) == 20
        assert reading.refunded is False

    async def test_repeat_credits_nothing(self, db_session) -> None:
        user = await _user(db_session)
        reading = await _ask(db_session, user, invoice=True, wallet=20)
        with patch(API, new=AsyncMock()) as api:
            assert await refund_ask_payment(db_session, reading, user.telegram_id) is True
            assert await refund_ask_payment(db_session, reading, user.telegram_id) is False
        api.assert_awaited_once()
        assert await _balance(db_session, user) == 20

    async def test_free_returns_false(self, db_session) -> None:
        user = await _user(db_session)
        reading = await _ask(db_session, user, invoice=False, wallet=0)
        assert await refund_ask_payment(db_session, reading, user.telegram_id) is False
