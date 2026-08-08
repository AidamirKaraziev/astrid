"""Подарочные разборы: выдача кода, правила активации, что получает новичок."""

from __future__ import annotations

import pytest

from astra.gifts import crud as gifts_crud
from astra.gifts.models import GiftStatus
from astra.payments.enums import CURRENCY_XTR
from astra.payments.models import Product, ProductPrice
from astra.services.gift_service import (
    GiftRedeemed,
    GiftRefusal,
    giftable_products,
    issue_gift,
    link_gift_on_start,
    redeem_gift,
)
from astra.telegram.utils import extract_gift_code, extract_referral_code
from astra.wallet import crud as wallet_crud

from conftest import new_test_telegram_id

PRODUCT = "tarot_three_cards"


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


async def _priced_product(session, code: str = PRODUCT, amount: int = 50) -> None:
    """Товар с ценой в каталоге: без неё дарить нечего."""
    existing = await session.get(Product, code)
    if existing is None:
        session.add(Product(code=code, kind="tarot", title="Три карты"))
        await session.flush()
    row = await session.execute(
        ProductPrice.__table__.select().where(
            ProductPrice.product_code == code,
            ProductPrice.currency == CURRENCY_XTR,
        ),
    )
    if row.first() is None:
        session.add(ProductPrice(product_code=code, currency=CURRENCY_XTR, amount=amount))
        await session.flush()


class TestDeepLink:
    def test_gift_and_referral_links_do_not_collide(self) -> None:
        assert extract_gift_code("gift_abc123") == "abc123"
        assert extract_gift_code("ref_abc123") is None
        assert extract_referral_code("gift_abc123") is None
        assert extract_gift_code(None) is None


class TestCatalog:
    def test_only_products_that_are_actually_sold(self) -> None:
        codes = {p.code for p in giftable_products()}
        assert PRODUCT in codes
        # Натал и совместимость не заведены как товары — дарить их нечего.
        assert "natal_report" not in codes
        assert "compatibility" not in codes

    def test_every_product_has_a_human_label(self) -> None:
        assert all(p.label.strip() for p in giftable_products())


@pytest.mark.asyncio
class TestIssuing:
    async def test_code_is_unique_and_readable(self, db_session) -> None:
        giver = await _user(db_session)

        first = await issue_gift(db_session, giver, PRODUCT)
        second = await issue_gift(db_session, giver, PRODUCT)

        assert first is not None and second is not None
        assert first.code != second.code
        # Ни нуля с буквой O, ни единицы с l: код читают с чужого экрана.
        assert not set(first.code) & set("01lIO")

    async def test_unredeemed_gifts_are_capped(self, db_session) -> None:
        """Дарить можно скольким угодно, но невостребованные ссылки не копятся."""
        from astra.core.config import get_settings

        giver = await _user(db_session)
        limit = get_settings().gift_max_unredeemed
        for _ in range(limit):
            assert await issue_gift(db_session, giver, PRODUCT) is not None

        assert await issue_gift(db_session, giver, PRODUCT) is None

    async def test_redeemed_gifts_do_not_count_against_the_cap(self, db_session) -> None:
        await _priced_product(db_session)
        giver = await _user(db_session)
        gift = await issue_gift(db_session, giver, PRODUCT)
        assert gift is not None
        await redeem_gift(db_session, gift.code, await _user(db_session), is_newcomer=True)

        assert await gifts_crud.count_unredeemed(db_session, giver.id) == 0


@pytest.mark.asyncio
class TestRedeeming:
    async def test_newcomer_gets_the_price_on_the_wallet(self, db_session) -> None:
        await _priced_product(db_session, amount=50)
        giver = await _user(db_session)
        gift = await issue_gift(db_session, giver, PRODUCT)
        newcomer = await _user(db_session)

        outcome = await redeem_gift(db_session, gift.code, newcomer, is_newcomer=True)

        assert isinstance(outcome, GiftRedeemed)
        assert outcome.stars == 50
        assert "Три карты" in outcome.label
        assert await wallet_crud.get_balance(db_session, newcomer.id) == 50
        assert gift.status is GiftStatus.REDEEMED
        assert gift.redeemed_by == newcomer.id

    async def test_registered_person_is_refused(self, db_session) -> None:
        """Подарок — канал роста, а не скидка тем, кто уже в боте."""
        await _priced_product(db_session)
        giver = await _user(db_session)
        gift = await issue_gift(db_session, giver, PRODUCT)
        old_timer = await _user(db_session)

        outcome = await redeem_gift(db_session, gift.code, old_timer, is_newcomer=False)

        assert outcome is GiftRefusal.NOT_A_NEWCOMER
        assert await wallet_crud.get_balance(db_session, old_timer.id) == 0
        assert gift.status is GiftStatus.ISSUED  # код не сгорел

    async def test_second_gift_from_the_same_giver_is_refused(self, db_session) -> None:
        """Иначе один человек раздаёт себе бесконечную ленту через новые аккаунты."""
        await _priced_product(db_session)
        giver = await _user(db_session)
        first = await issue_gift(db_session, giver, PRODUCT)
        second = await issue_gift(db_session, giver, PRODUCT)
        newcomer = await _user(db_session)
        await redeem_gift(db_session, first.code, newcomer, is_newcomer=True)

        outcome = await redeem_gift(db_session, second.code, newcomer, is_newcomer=True)

        assert outcome is GiftRefusal.ALREADY_GIFTED_BY_GIVER

    async def test_code_works_only_once(self, db_session) -> None:
        await _priced_product(db_session)
        giver = await _user(db_session)
        gift = await issue_gift(db_session, giver, PRODUCT)
        await redeem_gift(db_session, gift.code, await _user(db_session), is_newcomer=True)

        outcome = await redeem_gift(db_session, gift.code, await _user(db_session), is_newcomer=True)

        assert outcome is GiftRefusal.ALREADY_REDEEMED

    async def test_own_gift_is_refused(self, db_session) -> None:
        giver = await _user(db_session)
        gift = await issue_gift(db_session, giver, PRODUCT)

        assert await redeem_gift(db_session, gift.code, giver, is_newcomer=True) is (
            GiftRefusal.SELF_GIFT
        )

    async def test_unknown_code_is_refused(self, db_session) -> None:
        newcomer = await _user(db_session)
        outcome = await redeem_gift(db_session, "nosuchcode", newcomer, is_newcomer=True)
        assert outcome is GiftRefusal.UNKNOWN_CODE


@pytest.mark.asyncio
class TestLinkOnStart:
    async def test_gift_link_also_creates_the_referral(self, db_session) -> None:
        """Отдельную ссылку «пригласить» дарителю слать не нужно."""
        from astra.referrals import crud as referrals_crud

        giver = await _user(db_session)
        gift = await issue_gift(db_session, giver, PRODUCT)
        newcomer = await _user(db_session)

        code = await link_gift_on_start(db_session, newcomer, gift.code)

        assert code == gift.code
        referral = await referrals_crud.get_pending_referral_for_invitee(db_session, newcomer.id)
        assert referral is not None and referral.referrer_id == giver.id

    async def test_gift_is_not_spent_at_start(self, db_session) -> None:
        """Иначе его съел бы человек, бросивший регистрацию на первом экране."""
        giver = await _user(db_session)
        gift = await issue_gift(db_session, giver, PRODUCT)
        newcomer = await _user(db_session)

        await link_gift_on_start(db_session, newcomer, gift.code)

        assert gift.status is GiftStatus.ISSUED
        assert await wallet_crud.get_balance(db_session, newcomer.id) == 0

    async def test_unknown_code_links_nothing(self, db_session) -> None:
        newcomer = await _user(db_session)
        assert await link_gift_on_start(db_session, newcomer, "nosuchcode") is None
