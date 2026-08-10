"""Раздел «Пригласить друга»: экран, выдача подарка, ссылка в PDF."""

from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from aiogram.types import Message

from astra.reports.bot_link import resolve_telegram_bot_url
from astra.services.gift_service import giftable_products
from astra.telegram.button_texts import (
    CB_INVITE_GIFT,
    CB_INVITE_GIFT_PICK_PREFIX,
    CB_INVITE_HUB,
    CB_INVITE_LINK,
)
from astra.telegram.handlers.invites import (
    cb_invite_hub,
    cb_invite_link,
    cb_issue_gift,
    cb_pick_gift,
)

_MODULE = "astra.telegram.handlers.invites"
PRODUCT = "tarot_three_cards"


def _callback(data: str) -> MagicMock:
    callback = MagicMock()
    callback.data = data
    callback.answer = AsyncMock()
    callback.from_user = MagicMock(id=100500)
    callback.message = MagicMock(spec=Message)
    callback.message.answer = AsyncMock()
    return callback


def _stats() -> SimpleNamespace:
    return SimpleNamespace(
        code="abc123",
        referral_link="https://t.me/TestAstraBot?start=ref_abc123",
        invited_count=2,
        points_earned=0,
    )


def _mocks(**overrides) -> dict:
    defaults = {
        "users_crud.get_user_by_telegram_id": AsyncMock(return_value=MagicMock(id=uuid4())),
        "get_referral_stats": AsyncMock(return_value=_stats()),
        "get_balance": AsyncMock(return_value=30),
        "gifts_crud.count_redeemed": AsyncMock(return_value=1),
        "issue_gift": AsyncMock(return_value=SimpleNamespace(code="giftcode")),
        "show_screen": AsyncMock(return_value=555),
        "close_screen": AsyncMock(),
        "send_with_effect": AsyncMock(),
    }
    defaults.update(overrides)
    return defaults


async def _run(handler, mocks: dict, *args) -> None:
    with ExitStack() as stack:
        for name, mock in mocks.items():
            stack.enter_context(patch(f"{_MODULE}.{name}", mock))
        await handler(*args)


def _screen(mocks: dict) -> str:
    call = mocks["show_screen"].call_args
    assert call is not None, "экран раздела не обновлялся"
    return str(call.args[1])


class TestPdfLink:
    def test_cta_carries_the_owner_code(self) -> None:
        """PDF пересылают дальше — переход должен засчитаться тому, кто поделился."""
        assert resolve_telegram_bot_url("AstridBot", "ab12cd34") == (
            "https://t.me/AstridBot?start=ref_ab12cd34"
        )

    def test_without_code_it_is_a_plain_link(self) -> None:
        assert resolve_telegram_bot_url("AstridBot") == "https://t.me/AstridBot"


@pytest.mark.asyncio
class TestHub:
    async def test_shows_balance_and_stats(self) -> None:
        mocks = _mocks()

        await _run(cb_invite_hub, mocks, _callback(CB_INVITE_HUB), AsyncMock())

        text = _screen(mocks)
        assert "30 ⭐" in text  # баланс кошелька
        assert "<b>2</b>" in text  # приглашено
        assert "<b>1</b>" in text  # подарков забрали

    async def test_gift_picker_lists_the_catalog(self) -> None:
        mocks = _mocks()

        await _run(cb_pick_gift, mocks, _callback(CB_INVITE_GIFT))

        markup = mocks["show_screen"].call_args.kwargs["reply_markup"]
        data = [b.callback_data for row in markup.inline_keyboard for b in row]
        for product in giftable_products():
            assert f"{CB_INVITE_GIFT_PICK_PREFIX}{product.code}" in data

    async def test_link_screen_shows_the_referral_link(self) -> None:
        mocks = _mocks()

        await _run(cb_invite_link, mocks, _callback(CB_INVITE_LINK), AsyncMock())

        assert "ref_abc123" in _screen(mocks)

    @pytest.mark.parametrize(
        ("handler", "data"),
        [(cb_invite_hub, CB_INVITE_HUB), (cb_invite_link, CB_INVITE_LINK)],
    )
    async def test_stranger_hears_what_to_do(self, handler, data) -> None:
        """Незнакомого человека кнопка не имеет права проигнорировать молча."""
        callback = _callback(data)
        mocks = _mocks(**{"users_crud.get_user_by_telegram_id": AsyncMock(return_value=None)})

        await _run(handler, mocks, callback, AsyncMock())

        mocks["show_screen"].assert_not_awaited()
        callback.answer.assert_awaited_once()
        assert "/start" in callback.answer.await_args.args[0]
        assert callback.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
class TestIssuingFromTheBot:
    async def test_gift_card_is_a_separate_forwardable_message(self) -> None:
        """Карточку пересылают другу: живи она в экране, подарок исчез бы на следующем шаге."""
        callback = _callback(f"{CB_INVITE_GIFT_PICK_PREFIX}{PRODUCT}")
        mocks = _mocks()

        await _run(cb_issue_gift, mocks, callback, AsyncMock())

        mocks["close_screen"].assert_awaited_once()
        mocks["send_with_effect"].assert_awaited_once()
        card = mocks["send_with_effect"].call_args
        assert "Три карты" in str(card.args[1])
        url = card.kwargs["reply_markup"].inline_keyboard[0][0].url
        assert url.endswith("?start=gift_giftcode")

    async def test_card_does_not_mention_referrals(self) -> None:
        """Подарок должен читаться как подарок, а не как приглашение в схему."""
        mocks = _mocks()

        await _run(
            cb_issue_gift,
            mocks,
            _callback(f"{CB_INVITE_GIFT_PICK_PREFIX}{PRODUCT}"),
            AsyncMock(),
        )

        card = str(mocks["send_with_effect"].call_args.args[1]).lower()
        assert "реферал" not in card
        assert "приглас" not in card

    async def test_unknown_product_is_ignored(self) -> None:
        mocks = _mocks()

        await _run(
            cb_issue_gift,
            mocks,
            _callback(f"{CB_INVITE_GIFT_PICK_PREFIX}natal_report"),
            AsyncMock(),
        )

        mocks["issue_gift"].assert_not_awaited()

    async def test_limit_is_explained_in_the_screen(self) -> None:
        mocks = _mocks(issue_gift=AsyncMock(return_value=None))

        await _run(
            cb_issue_gift,
            mocks,
            _callback(f"{CB_INVITE_GIFT_PICK_PREFIX}{PRODUCT}"),
            AsyncMock(),
        )

        mocks["send_with_effect"].assert_not_awaited()
        assert "подарк" in _screen(mocks).lower()
