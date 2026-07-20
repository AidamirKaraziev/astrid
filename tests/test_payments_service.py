"""Тесты оплаты: каталог цен по валютам, снапшот в платеже, идемпотентность, refund."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from astra.payments.service import (
    ProductPriceInfo,
    get_tarot_price,
    parse_tarot_invoice_payload,
    refund_reading_payment,
    register_tarot_payment,
    tarot_invoice_payload,
    tarot_product_code,
)

_MODULE = "astra.payments.service"


class TestInvoicePayload:
    def test_roundtrip(self):
        reading_id = uuid4()
        assert parse_tarot_invoice_payload(tarot_invoice_payload(reading_id)) == reading_id

    def test_foreign_payload_returns_none(self):
        assert parse_tarot_invoice_payload("natal:123") is None
        assert parse_tarot_invoice_payload("tarot:не-uuid") is None
        assert parse_tarot_invoice_payload("") is None
        assert parse_tarot_invoice_payload(None) is None


class TestTarotPrice:
    def test_product_code_per_spread(self):
        assert tarot_product_code("wish") == "tarot_wish"

    async def test_price_from_catalog_row(self):
        row = MagicMock(currency="XTR", amount=75, discount_percent=20)
        with patch(
            f"{_MODULE}.payments_crud.get_product_price",
            AsyncMock(return_value=row),
        ) as get_price:
            price = await get_tarot_price(AsyncMock(), "wish")
        assert price == ProductPriceInfo("XTR", 75, 20)
        assert get_price.await_args.args[1] == "tarot_wish"
        assert get_price.await_args.args[2] == "XTR"

    async def test_other_currency_looked_up_separately(self):
        row = MagicMock(currency="RUB", amount=19900, discount_percent=0)
        with patch(
            f"{_MODULE}.payments_crud.get_product_price",
            AsyncMock(return_value=row),
        ) as get_price:
            price = await get_tarot_price(AsyncMock(), "wish", currency="RUB")
        assert price == ProductPriceInfo("RUB", 19900, 0)
        assert get_price.await_args.args[2] == "RUB"

    async def test_missing_xtr_row_falls_back_to_config(self):
        with patch(
            f"{_MODULE}.payments_crud.get_product_price",
            AsyncMock(return_value=None),
        ):
            price = await get_tarot_price(AsyncMock(), "wish")
        from astra.core.config import get_settings

        assert price.base_amount == get_settings().tarot_reading_price_stars
        assert price.currency == "XTR"
        assert not price.has_discount

    async def test_missing_other_currency_raises(self):
        import pytest

        with patch(
            f"{_MODULE}.payments_crud.get_product_price",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(ValueError):
                await get_tarot_price(AsyncMock(), "wish", currency="RUB")


class TestProductPriceInfo:
    def test_no_discount_final_equals_base(self):
        assert ProductPriceInfo("XTR", 50).final_amount == 50
        assert ProductPriceInfo("XTR", 50, 0).has_discount is False

    def test_discount_rounds_to_whole_units(self):
        assert ProductPriceInfo("XTR", 50, 90).final_amount == 5
        assert ProductPriceInfo("XTR", 50, 33).final_amount == 34  # 33.5 → до целой

    def test_discount_never_drops_below_one_unit(self):
        assert ProductPriceInfo("XTR", 1, 90).final_amount == 1
        assert ProductPriceInfo("XTR", 2, 99).final_amount == 1

    def test_full_discount_is_ignored(self):
        # 100% скидки бесплатный инвойс не создаёт — Stars требуют цену ≥ 1
        assert ProductPriceInfo("XTR", 50, 100).has_discount is False
        assert ProductPriceInfo("XTR", 50, 100).final_amount == 50


class TestRegisterTarotPayment:
    def _args(self):
        user = MagicMock(id=uuid4())
        reading = MagicMock(id=uuid4(), spread_type="wish")
        return user, reading

    async def test_creates_payment_with_price_snapshot(self):
        user, reading = self._args()
        created = MagicMock()
        with (
            patch(f"{_MODULE}.payments_crud.get_payment_by_charge", AsyncMock(return_value=None)),
            patch(
                f"{_MODULE}.get_tarot_price",
                AsyncMock(return_value=ProductPriceInfo("XTR", 50, 90)),
            ),
            patch(
                f"{_MODULE}.payments_crud.create_payment",
                AsyncMock(return_value=created),
            ) as create,
        ):
            payment = await register_tarot_payment(
                AsyncMock(),
                user=user,
                reading=reading,
                provider_charge_id="charge-1",
                amount=5,
                currency="XTR",
            )
        assert payment is created
        kwargs = create.await_args.kwargs
        assert kwargs["product_code"] == "tarot_wish"
        assert kwargs["provider"] == "telegram_stars"
        assert kwargs["provider_charge_id"] == "charge-1"
        assert kwargs["currency"] == "XTR"
        assert kwargs["amount"] == 5
        # снапшот каталога: оплата сошлась с ценой со скидкой
        assert kwargs["base_amount"] == 50
        assert kwargs["discount_percent"] == 90

    async def test_price_changed_midflight_snapshots_fact(self):
        user, reading = self._args()
        with (
            patch(f"{_MODULE}.payments_crud.get_payment_by_charge", AsyncMock(return_value=None)),
            patch(
                f"{_MODULE}.get_tarot_price",
                AsyncMock(return_value=ProductPriceInfo("XTR", 100, 0)),  # цену уже подняли
            ),
            patch(f"{_MODULE}.payments_crud.create_payment", AsyncMock()) as create,
        ):
            await register_tarot_payment(
                AsyncMock(),
                user=user,
                reading=reading,
                provider_charge_id="charge-1",
                amount=50,  # а заплатили по старому инвойсу
                currency="XTR",
            )
        kwargs = create.await_args.kwargs
        assert kwargs["amount"] == 50
        assert kwargs["base_amount"] == 50  # факт важнее каталога
        assert kwargs["discount_percent"] == 0

    async def test_duplicate_charge_returns_none(self):
        user, reading = self._args()
        with (
            patch(
                f"{_MODULE}.payments_crud.get_payment_by_charge",
                AsyncMock(return_value=MagicMock()),  # уже записан
            ),
            patch(f"{_MODULE}.payments_crud.create_payment", AsyncMock()) as create,
        ):
            payment = await register_tarot_payment(
                AsyncMock(),
                user=user,
                reading=reading,
                provider_charge_id="charge-1",
                amount=50,
                currency="XTR",
            )
        assert payment is None
        create.assert_not_awaited()


class TestRefundReadingPayment:
    async def test_refunds_and_marks(self):
        payment = MagicMock(provider_charge_id="charge-1")
        with (
            patch(
                f"{_MODULE}.payments_crud.get_completed_payment_for_reading",
                AsyncMock(return_value=payment),
            ),
            patch(f"{_MODULE}.refund_star_payment_api", AsyncMock()) as api,
            patch(f"{_MODULE}.payments_crud.mark_payment_refunded", AsyncMock()) as mark,
        ):
            assert await refund_reading_payment(AsyncMock(), MagicMock(id=uuid4()), 42) is True
        api.assert_awaited_once()
        assert api.await_args.args[0] == 42
        assert api.await_args.args[1] == "charge-1"
        mark.assert_awaited_once()

    async def test_no_payment_returns_false(self):
        with (
            patch(
                f"{_MODULE}.payments_crud.get_completed_payment_for_reading",
                AsyncMock(return_value=None),
            ),
            patch(f"{_MODULE}.refund_star_payment_api", AsyncMock()) as api,
        ):
            assert await refund_reading_payment(AsyncMock(), MagicMock(id=uuid4()), 42) is False
        api.assert_not_awaited()

    async def test_api_failure_keeps_payment_completed(self):
        payment = MagicMock(provider_charge_id="charge-1")
        with (
            patch(
                f"{_MODULE}.payments_crud.get_completed_payment_for_reading",
                AsyncMock(return_value=payment),
            ),
            patch(
                f"{_MODULE}.refund_star_payment_api",
                AsyncMock(side_effect=RuntimeError("api down")),
            ),
            patch(f"{_MODULE}.payments_crud.mark_payment_refunded", AsyncMock()) as mark,
        ):
            assert await refund_reading_payment(AsyncMock(), MagicMock(id=uuid4()), 42) is False
        mark.assert_not_awaited()
