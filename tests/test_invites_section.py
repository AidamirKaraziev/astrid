"""Раздел «Пригласить друга»: экран, выдача подарка, ссылка в PDF."""

from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from aiogram.types import Message

from astra.reports.bot_link import resolve_telegram_bot_url
from astra.services.gift_service import GiftableProduct
from astra.gifts.models import GiftStatus
from astra.telegram.button_texts import (
    CB_INVITE_GIFT,
    CB_INVITE_GIFT_PICK_PREFIX,
    CB_INVITE_GIFT_REVOKE_ASK_PREFIX,
    CB_INVITE_GIFT_REVOKE_DO_PREFIX,
    CB_INVITE_GIFT_SHOW_PREFIX,
    CB_INVITE_GIFTS,
    CB_INVITE_HUB,
    CB_INVITE_LINK,
)
from astra.telegram.handlers.invites import (
    cb_invite_hub,
    cb_invite_link,
    cb_issue_gift,
    cb_my_gifts,
    cb_pick_gift,
    cb_revoke_ask,
    cb_revoke_do,
    cb_show_gift,
)

_MODULE = "astra.telegram.handlers.invites"
PRODUCT = "tarot_three_cards"
# Витрина: то, что можно подарить сейчас. Бесплатное сегодня сюда не попадает,
# поэтому список задаём явно, а не берём из каталога.
_OFFERS = [
    GiftableProduct(PRODUCT, "🃏 Три карты", price_stars=50),
    GiftableProduct("ask_love_kids", "💬 Будут ли у меня дети", price_stars=1),
]


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
        "gifts_crud.count_unredeemed": AsyncMock(return_value=3),
        "referral_earnings": AsyncMock(return_value=20),
        "gifts_crud.list_by_giver": AsyncMock(return_value=[]),
        "gifts_crud.get_by_code": AsyncMock(return_value=None),
        "giftable_offers": AsyncMock(return_value=_OFFERS),
        "issue_gift": AsyncMock(return_value=SimpleNamespace(code="giftcode")),
        "revoke_gift": AsyncMock(return_value=None),
        "show_screen": AsyncMock(return_value=555),
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


def _screen_callbacks(mocks: dict) -> list[str]:
    markup = mocks["show_screen"].call_args.kwargs["reply_markup"]
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


_OWNER_ID = uuid4()


def _owner() -> MagicMock:
    return MagicMock(id=_OWNER_ID)


def _gift(
    code: str = "giftcode",
    *,
    giver_id=None,
    status=GiftStatus.ISSUED,
    created_at=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        code=code,
        product_code=PRODUCT,
        giver_id=_OWNER_ID if giver_id is None else giver_id,
        status=status,
        created_at=created_at or datetime(2026, 8, 3, tzinfo=UTC),
    )


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
        assert "30 ⭐" in text  # весь кошелёк
        assert "20 ⭐" in text  # из него — заработанное на друзьях
        assert "<b>2</b>" in text  # друзей пришло
        assert "<b>3</b>" in text  # ссылок в пути
        assert "потолка нет" in text

    async def test_gifts_are_not_counted_as_a_second_arrival(self) -> None:
        """Подарок ставит и реферальную привязку — забранные подарки сидят в «пришло»."""
        mocks = _mocks()

        await _run(cb_invite_hub, mocks, _callback(CB_INVITE_HUB), AsyncMock())

        assert "забрали" not in _screen(mocks).lower()

    async def test_gift_picker_lists_what_can_be_gifted_now(self) -> None:
        mocks = _mocks()

        await _run(cb_pick_gift, mocks, _callback(CB_INVITE_GIFT), AsyncMock())

        data = _screen_callbacks(mocks)
        for product in _OFFERS:
            assert f"{CB_INVITE_GIFT_PICK_PREFIX}{product.code}" in data

    async def test_price_is_on_the_button(self) -> None:
        """Даритель платит не своими, но вес подарка видеть должен."""
        mocks = _mocks()

        await _run(cb_pick_gift, mocks, _callback(CB_INVITE_GIFT), AsyncMock())

        markup = mocks["show_screen"].call_args.kwargs["reply_markup"]
        labels = [b.text for row in markup.inline_keyboard for b in row]
        assert any("50 ⭐" in label for label in labels)

    async def test_empty_shelf_is_not_a_broken_screen(self) -> None:
        """Всё роздано даром — дарить нечего, и это правда, а не поломка."""
        mocks = _mocks(giftable_offers=AsyncMock(return_value=[]))

        await _run(cb_pick_gift, mocks, _callback(CB_INVITE_GIFT), AsyncMock())

        assert "дарить нечего" in _screen(mocks).lower()
        assert not [c for c in _screen_callbacks(mocks) if c.startswith(CB_INVITE_GIFT_PICK_PREFIX)]

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
    async def test_issued_gift_stays_on_the_screen_with_its_link(self) -> None:
        """Карточка «Тебе подарок» в своём же чате читалась как подарок себе."""
        mocks = _mocks()
        callback = _callback(f"{CB_INVITE_GIFT_PICK_PREFIX}{PRODUCT}")

        await _run(cb_issue_gift, mocks, callback, AsyncMock())

        callback.message.answer.assert_not_awaited()  # в чат не падает ничего
        screen = _screen(mocks)
        assert "Три карты" in screen
        assert "start=gift_giftcode" in screen  # ссылку видно и можно скопировать

    async def test_sending_is_one_tap_not_a_manual_forward(self) -> None:
        mocks = _mocks()

        await _run(
            cb_issue_gift,
            mocks,
            _callback(f"{CB_INVITE_GIFT_PICK_PREFIX}{PRODUCT}"),
            AsyncMock(),
        )

        markup = mocks["show_screen"].call_args.kwargs["reply_markup"]
        share = markup.inline_keyboard[0][0]
        assert share.url.startswith("https://t.me/share/url?url=")
        assert "start%3Dgift_giftcode" in share.url or "start=gift_giftcode" in share.url

    async def test_what_goes_to_the_friend_reads_as_a_gift(self) -> None:
        """Подарок должен читаться как подарок, а не как приглашение в схему."""
        from astra.telegram.handlers.invites import _GIFT_PITCH

        pitch = _GIFT_PITCH.lower()
        assert "реферал" not in pitch
        assert "приглас" not in pitch
        assert "подар" in pitch or "дарю" in pitch

    async def test_product_outside_the_shelf_is_refused_with_words(self) -> None:
        """Кнопка могла остаться от прошлого экрана, а товар — уйти в бесплатные."""
        mocks = _mocks()
        callback = _callback(f"{CB_INVITE_GIFT_PICK_PREFIX}natal_report")

        await _run(cb_issue_gift, mocks, callback, AsyncMock())

        mocks["issue_gift"].assert_not_awaited()
        assert callback.answer.await_args.args[0].strip()
        assert callback.answer.await_args.kwargs["show_alert"] is True


    async def test_giving_never_hits_a_ceiling(self) -> None:
        """Подарки — канал привлечения: тот, кто приводит людей, в стену не упирается."""
        mocks = _mocks(**{"gifts_crud.count_unredeemed": AsyncMock(return_value=500)})

        await _run(cb_pick_gift, mocks, _callback(CB_INVITE_GIFT), AsyncMock())

        data = _screen_callbacks(mocks)
        assert [c for c in data if c.startswith(CB_INVITE_GIFT_PICK_PREFIX)]


@pytest.mark.asyncio
class TestMyGifts:
    """Выданная ссылка жила в одном сообщении: удалил — и подарок недостижим."""

    async def test_waiting_gifts_are_listed_with_a_row_each(self) -> None:
        mocks = _mocks(
            **{"gifts_crud.list_by_giver": AsyncMock(return_value=[_gift("aaa"), _gift("bbb")])},
        )

        await _run(cb_my_gifts, mocks, _callback(CB_INVITE_GIFTS), AsyncMock())

        callbacks = _screen_callbacks(mocks)
        assert f"{CB_INVITE_GIFT_SHOW_PREFIX}aaa" in callbacks
        assert f"{CB_INVITE_GIFT_SHOW_PREFIX}bbb" in callbacks

    async def test_rows_of_the_same_product_are_told_apart_by_date(self) -> None:
        """Десять «Трёх карт» одной подписью — отзыв наугад."""
        mocks = _mocks(
            **{
                "gifts_crud.list_by_giver": AsyncMock(
                    return_value=[
                        _gift("aaa", created_at=datetime(2026, 8, 3, tzinfo=UTC)),
                        _gift("bbb", created_at=datetime(2026, 8, 11, tzinfo=UTC)),
                    ],
                ),
            },
        )

        await _run(cb_my_gifts, mocks, _callback(CB_INVITE_GIFTS), AsyncMock())

        labels = [
            b.text
            for row in mocks["show_screen"].call_args.kwargs["reply_markup"].inline_keyboard
            for b in row
        ]
        assert "03.08" in " ".join(labels)
        assert "11.08" in " ".join(labels)
        assert len(set(labels)) == len(labels)

    async def test_empty_shelf_says_so(self) -> None:
        mocks = _mocks()

        await _run(cb_my_gifts, mocks, _callback(CB_INVITE_GIFTS), AsyncMock())

        assert "Ни одной ссылки в пути" in _screen(mocks)

    async def test_link_is_copyable_text_not_only_a_button(self) -> None:
        """Её отправляют и вне Telegram, и по ней подарок находится заново."""
        mocks = _mocks(
            **{
                "users_crud.get_user_by_telegram_id": AsyncMock(return_value=_owner()),
                "gifts_crud.get_by_code": AsyncMock(return_value=_gift("aaa")),
            },
        )

        await _run(
            cb_show_gift,
            mocks,
            _callback(f"{CB_INVITE_GIFT_SHOW_PREFIX}aaa"),
            AsyncMock(),
        )

        assert "<code>" in _screen(mocks)
        assert "start=gift_aaa" in _screen(mocks)

    async def test_someone_elses_gift_is_not_shown(self) -> None:
        mocks = _mocks(
            **{
                "users_crud.get_user_by_telegram_id": AsyncMock(return_value=_owner()),
                "gifts_crud.get_by_code": AsyncMock(return_value=_gift("aaa", giver_id=uuid4())),
            },
        )

        await _run(
            cb_show_gift,
            mocks,
            _callback(f"{CB_INVITE_GIFT_SHOW_PREFIX}aaa"),
            AsyncMock(),
        )

        assert "start=gift_aaa" not in _screen(mocks)


@pytest.mark.asyncio
class TestRevoking:
    async def test_revoke_asks_first(self) -> None:
        """Ссылка может быть уже у друга — рвать её одним касанием нельзя."""
        mocks = _mocks(
            **{
                "users_crud.get_user_by_telegram_id": AsyncMock(return_value=_owner()),
                "gifts_crud.get_by_code": AsyncMock(return_value=_gift("aaa")),
            },
        )

        await _run(
            cb_revoke_ask,
            mocks,
            _callback(f"{CB_INVITE_GIFT_REVOKE_ASK_PREFIX}aaa"),
            AsyncMock(),
        )

        mocks["revoke_gift"].assert_not_awaited()
        assert f"{CB_INVITE_GIFT_REVOKE_DO_PREFIX}aaa" in _screen_callbacks(mocks)
        assert f"{CB_INVITE_GIFT_SHOW_PREFIX}aaa" in _screen_callbacks(mocks)  # передумать

    async def test_confirmed_revoke_frees_the_slot_and_returns_to_the_list(self) -> None:
        mocks = _mocks(
            **{
                "users_crud.get_user_by_telegram_id": AsyncMock(return_value=_owner()),
                "revoke_gift": AsyncMock(return_value=_gift("aaa", status=GiftStatus.REVOKED)),
            },
        )
        callback = _callback(f"{CB_INVITE_GIFT_REVOKE_DO_PREFIX}aaa")

        await _run(cb_revoke_do, mocks, callback, AsyncMock())

        assert mocks["revoke_gift"].await_args.args[2] == "aaa"
        assert "Отозвала" in callback.answer.await_args.args[0]
        assert "Мои подарки" in _screen(mocks)

    async def test_nothing_left_to_revoke_is_said_out_loud(self) -> None:
        """Немой ответ на «Да, отозвать» читается как несработавшая кнопка."""
        mocks = _mocks(**{"users_crud.get_user_by_telegram_id": AsyncMock(return_value=_owner())})
        callback = _callback(f"{CB_INVITE_GIFT_REVOKE_DO_PREFIX}aaa")

        await _run(cb_revoke_do, mocks, callback, AsyncMock())

        assert callback.answer.await_args.args[0].strip()


class TestCallbackNamespace:
    def test_branches_do_not_swallow_each_other(self) -> None:
        """`invite:gift:` был бы префиксом и для выбора товара, и для показа."""
        branches = [
            CB_INVITE_GIFT_PICK_PREFIX,
            CB_INVITE_GIFT_SHOW_PREFIX,
            CB_INVITE_GIFT_REVOKE_ASK_PREFIX,
            CB_INVITE_GIFT_REVOKE_DO_PREFIX,
        ]
        for one in branches:
            for other in branches:
                assert one == other or not one.startswith(other)
