"""Экран «Звёзды»: пришедшие деньги отдельно от напечатанных обязательств."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from astra.admin.render_stars import stars_page
from astra.admin.stars import (
    GIFT_PREFIX,
    REWARD_PREFIX,
    WELCOME_PREFIX,
    Stars,
    TelegramStars,
    Transaction,
    Wallet,
    telegram_stars,
    wallet_liability,
)
from astra.referrals import crud as referrals_crud
from astra.services.gift_service import issue_gift, redeem_gift
from astra.services.referral_service import (
    apply_referral_on_start,
    grant_invitee_welcome,
    reward_referrer_on_return,
)
from astra.wallet import crud as wallet_crud
from astra.wallet.models import WalletReason

from conftest import new_test_telegram_id

_MODULE = "astra.admin.stars"


def _txn(amount: int, *, incoming: bool) -> dict:
    """Операция в форме Bot API: у прихода есть source, у расхода — receiver."""
    partner = {"type": "user", "user": {"id": 7, "username": "masha"}}
    return {
        "id": "x",
        "amount": amount,
        "date": int(datetime(2026, 8, 14, 12, 0, tzinfo=UTC).timestamp()),
        "source": partner if incoming else None,
        "receiver": None if incoming else partner,
    }


def _api(*, balance: int = 4830, transactions=()) -> AsyncMock:
    """Ответы Bot API по методам — панель зовёт его по HTTP, без aiogram."""
    replies = {
        "getMyStarBalance": {"amount": balance},
        "getStarTransactions": {"transactions": list(transactions)},
    }
    return AsyncMock(side_effect=lambda method, payload=None: replies[method])


class TestWalletArithmetic:
    def test_minted_is_the_sum_of_its_parts(self) -> None:
        wallet = Wallet(rewards=120, welcome=14, gifts=350, other=13)
        assert wallet.minted == 497

    def test_empty_wallet_is_not_a_division(self) -> None:
        assert Wallet().minted == 0


@pytest.mark.asyncio
class TestTelegramSide:
    async def test_incoming_and_outgoing_are_told_apart(self) -> None:
        api = _api(transactions=[_txn(50, incoming=True), _txn(30, incoming=False)])

        with patch(f"{_MODULE}.call_bot_api", api):
            data = await telegram_stars()

        assert data.alive
        assert data.balance == 4830
        assert data.incoming == 50
        assert data.outgoing == 30
        assert [t.incoming for t in data.transactions] == [True, False]

    async def test_counterparty_prefers_the_username(self) -> None:
        with patch(f"{_MODULE}.call_bot_api", _api(transactions=[_txn(50, incoming=True)])):
            data = await telegram_stars()

        assert data.transactions[0].counterparty == "@masha"

    async def test_bot_api_failure_does_not_kill_the_page(self) -> None:
        """Внутренняя половина считается по своей базе и остаётся верной."""
        broken = AsyncMock(side_effect=RuntimeError("Unauthorized"))

        with patch(f"{_MODULE}.call_bot_api", broken):
            data = await telegram_stars()

        assert not data.alive
        assert "Unauthorized" in (data.error or "")
        assert stars_page(Stars(telegram=data, wallet=Wallet(gifts=350)))


@pytest.mark.asyncio
class TestLiabilityFromTheLedger:
    """Награда, приветствие и подарок носят одну причину — различает payload."""

    async def _user(self, session):
        from astra.users import crud as users_crud

        user = await users_crud.create_user(
            session,
            telegram_id=new_test_telegram_id(),
            username=None,
            language_code="ru",
        )
        await session.flush()
        return user

    async def test_each_kind_of_minting_lands_in_its_own_column(self, db_session) -> None:
        inviter = await self._user(db_session)
        invitee = await self._user(db_session)
        code = await referrals_crud.get_or_create_referral_code(db_session, inviter.id)
        await apply_referral_on_start(db_session, invitee, code.code)
        before = await wallet_liability(db_session)

        await grant_invitee_welcome(db_session, invitee)
        await reward_referrer_on_return(db_session, invitee)

        after = await wallet_liability(db_session)
        assert after.rewards > before.rewards
        assert after.welcome > before.welcome
        assert after.gifts == before.gifts

    async def test_a_redeemed_gift_shows_up_as_a_gift(self, db_session) -> None:
        from astra.payments.enums import CURRENCY_XTR
        from astra.payments.models import Product, ProductPrice

        code = "tarot_three_cards"
        if await db_session.get(Product, code) is None:
            db_session.add(Product(code=code, kind="tarot", title="Три карты"))
            await db_session.flush()
        rows = await db_session.execute(
            ProductPrice.__table__.select().where(ProductPrice.product_code == code),
        )
        if rows.first() is None:
            db_session.add(ProductPrice(product_code=code, currency=CURRENCY_XTR, amount=50))
            await db_session.flush()

        giver = await self._user(db_session)
        gift = await issue_gift(db_session, giver, code)
        before = await wallet_liability(db_session)

        await redeem_gift(db_session, gift.code, await self._user(db_session), is_newcomer=True)

        after = await wallet_liability(db_session)
        assert after.gifts == before.gifts + 50
        assert after.rewards == before.rewards

    async def test_spending_is_counted_apart_from_minting(self, db_session) -> None:
        """Потраченное из кошелька — выручка, которую мы не получили."""
        user = await self._user(db_session)
        await wallet_crud.add_entry(
            db_session,
            user.id,
            50,
            WalletReason.REFERRAL_REWARD,
            payload=f"{GIFT_PREFIX}whatever",
        )
        before = await wallet_liability(db_session)

        await wallet_crud.add_entry(db_session, user.id, -20, WalletReason.PURCHASE)

        after = await wallet_liability(db_session)
        assert after.spent == before.spent + 20
        assert after.minted == before.minted  # трата ничего не печатает
        assert after.outstanding == before.outstanding - 20


class TestPage:
    def test_the_two_halves_are_not_added_up(self) -> None:
        """Складывать настоящие деньги и напечатанные нельзя — это разные вещи."""
        page = stars_page(
            Stars(
                telegram=TelegramStars(
                    balance=4830,
                    transactions=(Transaction(datetime.now(UTC), 50, True, "@masha"),),
                ),
                wallet=Wallet(rewards=120, welcome=14, gifts=350, spent=200, outstanding=284),
            ),
        )

        assert "4 830 ⭐" in page  # баланс Telegram
        assert "484 ⭐" in page  # напечатано даром, отдельной цифрой
        assert "5314" not in page.replace(" ", "")  # и нигде не сложено с балансом

    def test_the_screen_does_not_drag_aiogram_into_the_panel(self) -> None:
        """Панель едет отдельным процессом, в котором бота нет."""
        import ast

        import astra.admin.stars

        tree = ast.parse(Path(astra.admin.stars.__file__).read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)

        assert not [n for n in imported if "aiogram" in n or "astra.telegram" in n]

    def test_prefixes_stay_in_sync_with_the_ledger(self) -> None:
        """Разъедься они с payload начислений — все колонки станут нулями."""
        from astra.services.referral_service import REWARD_PAYLOAD_PREFIX

        assert REWARD_PREFIX == REWARD_PAYLOAD_PREFIX
        assert WELCOME_PREFIX == "ref_welcome:"
        assert GIFT_PREFIX == "gift:"
