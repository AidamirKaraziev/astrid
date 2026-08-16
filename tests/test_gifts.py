"""Подарочные разборы: выдача кода, правила активации, что получает новичок."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from astra.gifts import crud as gifts_crud
from astra.gifts.models import GiftStatus
from astra.payments.enums import CURRENCY_XTR
from astra.payments.models import Product, ProductPrice
from astra.services.gift_service import (
    GiftRedeemed,
    GiftRefusal,
    gift_slots_left,
    giftable_offers,
    giftable_products,
    issue_gift,
    link_gift_on_start,
    redeem_gift,
    revoke_gift,
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

    def test_questions_are_marked_apart_from_spreads(self) -> None:
        """Заголовков у inline-клавиатуры не бывает — ветки различает значок."""
        labels = {p.code: p.label for p in giftable_products()}
        assert labels["ask_love_kids"].startswith("💬")
        assert not labels[PRODUCT].startswith("💬")


@pytest.mark.asyncio
class TestShelf:
    """Витрина — то, что можно подарить сейчас, а не весь каталог."""

    async def test_price_comes_with_the_offer(self, db_session) -> None:
        await _priced_product(db_session, amount=50)

        offers = {p.code: p for p in await giftable_offers(db_session)}

        assert offers[PRODUCT].price_stars == 50

    async def test_free_today_is_not_offered_as_a_gift(self, db_session) -> None:
        """Дарить то, что друг и так возьмёт даром, — пустой жест и кран звёзд."""
        await _priced_product(db_session)
        await db_session.execute(
            ProductPrice.__table__.update()
            .where(ProductPrice.product_code == PRODUCT)
            .values(discount_percent=100),
        )
        await db_session.flush()

        assert PRODUCT not in {p.code for p in await giftable_offers(db_session)}

    async def test_product_without_a_price_is_not_offered(self, db_session) -> None:
        assert "natal_report" not in {p.code for p in await giftable_offers(db_session)}


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
class TestRevoking:
    """Без отзыва потолок выбирается брошенными новичками — и навсегда."""

    async def test_revoke_frees_a_slot(self, db_session) -> None:
        from astra.core.config import get_settings

        giver = await _user(db_session)
        limit = get_settings().gift_max_unredeemed
        gifts = [await issue_gift(db_session, giver, PRODUCT) for _ in range(limit)]
        assert await gift_slots_left(db_session, giver) == 0

        assert await revoke_gift(db_session, giver, gifts[0].code) is not None

        assert await gift_slots_left(db_session, giver) == 1
        assert await issue_gift(db_session, giver, PRODUCT) is not None

    async def test_revoked_link_stops_working(self, db_session) -> None:
        giver = await _user(db_session)
        gift = await issue_gift(db_session, giver, PRODUCT)

        await revoke_gift(db_session, giver, gift.code)

        assert gift.status is GiftStatus.REVOKED
        assert await redeem_gift(db_session, gift.code, await _user(db_session), is_newcomer=True) is (
            GiftRefusal.REVOKED
        )

    async def test_someone_elses_gift_cannot_be_revoked(self, db_session) -> None:
        giver = await _user(db_session)
        gift = await issue_gift(db_session, giver, PRODUCT)

        assert await revoke_gift(db_session, await _user(db_session), gift.code) is None
        assert gift.status is GiftStatus.ISSUED

    async def test_taken_gift_cannot_be_revoked(self, db_session) -> None:
        """Там уже потрачены звёзды — отзывать нечего."""
        await _priced_product(db_session)
        giver = await _user(db_session)
        gift = await issue_gift(db_session, giver, PRODUCT)
        await redeem_gift(db_session, gift.code, await _user(db_session), is_newcomer=True)

        assert await revoke_gift(db_session, giver, gift.code) is None
        assert gift.status is GiftStatus.REDEEMED

    async def test_revoked_gifts_stay_out_of_the_list(self, db_session) -> None:
        giver = await _user(db_session)
        kept = await issue_gift(db_session, giver, PRODUCT)
        dropped = await issue_gift(db_session, giver, PRODUCT)
        await revoke_gift(db_session, giver, dropped.code)

        waiting = await gifts_crud.list_by_giver(db_session, giver.id, status=GiftStatus.ISSUED)

        assert [g.code for g in waiting] == [kept.code]


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

        code = await link_gift_on_start(db_session, newcomer, gift.code, is_newcomer=True)

        assert code == gift.code
        referral = await referrals_crud.get_pending_referral_for_invitee(db_session, newcomer.id)
        assert referral is not None and referral.referrer_id == giver.id

    async def test_gift_is_not_spent_at_start(self, db_session) -> None:
        """Иначе его съел бы человек, бросивший регистрацию на первом экране."""
        giver = await _user(db_session)
        gift = await issue_gift(db_session, giver, PRODUCT)
        newcomer = await _user(db_session)

        await link_gift_on_start(db_session, newcomer, gift.code, is_newcomer=True)

        assert gift.status is GiftStatus.ISSUED
        assert await wallet_crud.get_balance(db_session, newcomer.id) == 0

    async def test_plain_link_says_nothing(self, db_session) -> None:
        """Ссылка была не подарочная — и говорить не о чем."""
        newcomer = await _user(db_session)
        assert await link_gift_on_start(db_session, newcomer, None, is_newcomer=True) is None


@pytest.mark.asyncio
class TestRefusalHasAReason:
    """Человек нажал «Забрать подарок»: молча показать ему меню — поломка.

    Каждый отказ на входе называет причину, и ни один не сжигает код: ссылка
    остаётся годной для того, кому она предназначалась.
    """

    async def test_unknown_code(self, db_session) -> None:
        newcomer = await _user(db_session)

        outcome = await link_gift_on_start(
            db_session,
            newcomer,
            "nosuchcode",
            is_newcomer=True,
        )

        assert outcome is GiftRefusal.UNKNOWN_CODE

    async def test_already_redeemed_code(self, db_session) -> None:
        await _priced_product(db_session)
        giver = await _user(db_session)
        gift = await issue_gift(db_session, giver, PRODUCT)
        await redeem_gift(db_session, gift.code, await _user(db_session), is_newcomer=True)

        outcome = await link_gift_on_start(
            db_session,
            await _user(db_session),
            gift.code,
            is_newcomer=True,
        )

        assert outcome is GiftRefusal.ALREADY_REDEEMED

    async def test_revoked_code_is_not_confused_with_a_taken_one(self, db_session) -> None:
        giver = await _user(db_session)
        gift = await issue_gift(db_session, giver, PRODUCT)
        await revoke_gift(db_session, giver, gift.code)

        outcome = await link_gift_on_start(
            db_session,
            await _user(db_session),
            gift.code,
            is_newcomer=True,
        )

        assert outcome is GiftRefusal.REVOKED

    async def test_registered_person_hears_why(self, db_session) -> None:
        giver = await _user(db_session)
        gift = await issue_gift(db_session, giver, PRODUCT)
        old_timer = await _user(db_session)

        outcome = await link_gift_on_start(
            db_session,
            old_timer,
            gift.code,
            is_newcomer=False,
        )

        assert outcome is GiftRefusal.NOT_A_NEWCOMER
        assert gift.status is GiftStatus.ISSUED  # ссылка ждёт своего человека

    async def test_own_link_is_named_as_such(self, db_session) -> None:
        """Даритель не новичок, и общий отказ спрятал бы от него настоящую причину."""
        giver = await _user(db_session)
        gift = await issue_gift(db_session, giver, PRODUCT)

        outcome = await link_gift_on_start(db_session, giver, gift.code, is_newcomer=False)

        assert outcome is GiftRefusal.SELF_GIFT


class TestRefusalWording:
    def test_every_refusal_has_words_for_a_human(self) -> None:
        """Новая причина без текста упала бы `KeyError` в лицо человеку."""
        from astra.services.gift_delivery import refusal_text

        for refusal in GiftRefusal:
            assert refusal_text(refusal).strip()


def _callbacks_of(markup) -> set[str]:
    return {b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data}


class TestOpenGiftButton:
    """Без кнопки подарок — тупик: новичок пять минут как в боте и меню не знает."""

    def test_every_giftable_product_can_be_opened(self) -> None:
        from astra.services.gift_delivery import open_gift_keyboard

        for product in giftable_products():
            assert open_gift_keyboard(product.code) is not None, product.code

    def test_button_presses_the_same_entry_as_the_menu(self) -> None:
        """Подарок не заводит своей ветки сценария — он жмёт кнопку за человека."""
        from astra.services.gift_delivery import open_gift_keyboard
        from astra.telegram.keyboards import ask_questions_keyboard, tarot_spreads_keyboard

        known = _callbacks_of(tarot_spreads_keyboard())
        known |= _callbacks_of(ask_questions_keyboard("love", "женщина"))

        for product in giftable_products():
            markup = open_gift_keyboard(product.code)
            assert _callbacks_of(markup) <= known, product.code

    def test_product_gone_from_the_catalog_gets_no_button(self) -> None:
        from astra.services.gift_delivery import open_gift_keyboard

        assert open_gift_keyboard("natal_report") is None


@pytest.mark.asyncio
class TestDeliveryAtTheEndOfOnboarding:
    async def test_newcomer_gets_the_gift_with_a_way_to_open_it(self, db_session) -> None:
        from astra.services.gift_delivery import redeem_pending_gift
        from astra.telegram.button_texts import CB_TAROT_SPREAD_PREFIX

        await _priced_product(db_session)
        giver = await _user(db_session)
        gift = await issue_gift(db_session, giver, PRODUCT)
        message = AsyncMock()

        outcome = await redeem_pending_gift(
            message,
            db_session,
            await _user(db_session),
            gift.code,
        )

        assert isinstance(outcome, GiftRedeemed)
        sent = message.answer.await_args
        assert "Три карты" in sent.args[0]
        button = sent.kwargs["reply_markup"].inline_keyboard[0][0]
        assert button.callback_data == f"{CB_TAROT_SPREAD_PREFIX}three_cards"

    async def test_gift_taken_meanwhile_is_explained(self, db_session) -> None:
        """Пока человек регистрировался, код мог забрать кто-то другой."""
        from astra.services.gift_delivery import redeem_pending_gift

        await _priced_product(db_session)
        giver = await _user(db_session)
        gift = await issue_gift(db_session, giver, PRODUCT)
        await redeem_gift(db_session, gift.code, await _user(db_session), is_newcomer=True)
        latecomer = await _user(db_session)
        message = AsyncMock()

        outcome = await redeem_pending_gift(message, db_session, latecomer, gift.code)

        assert outcome is None
        assert "уже забрали" in message.answer.await_args.args[0]

    async def test_nothing_is_said_when_there_was_no_gift(self, db_session) -> None:
        from astra.services.gift_delivery import redeem_pending_gift

        message = AsyncMock()

        assert await redeem_pending_gift(message, db_session, await _user(db_session), None) is None
        message.answer.assert_not_awaited()


def _start_message() -> AsyncMock:
    message = AsyncMock()
    message.from_user.id = 42
    message.from_user.username = "aid"
    message.from_user.language_code = "ru"
    message.answer = AsyncMock()
    return message


@pytest.mark.anyio
class TestStartExplainsTheGift:
    """Вход по подарочной ссылке. Молчаливое главное меню читается как поломка."""

    async def test_registered_person_hears_why_instead_of_a_bare_menu(self) -> None:
        from astra.telegram.handlers.start import cmd_start

        message = _start_message()
        user = SimpleNamespace(
            id=1,
            onboarding_completed=True,
            bot_blocked_at=None,
            profile=SimpleNamespace(gender="женщина"),
        )

        with (
            patch(
                "astra.telegram.handlers.start.users_crud.get_user_by_telegram_id",
                new_callable=AsyncMock,
                return_value=user,
            ),
            patch("astra.telegram.handlers.start.sync_user_from_telegram", new_callable=AsyncMock),
            patch("astra.telegram.handlers.start.register_daily_activity", new_callable=AsyncMock),
            patch(
                "astra.telegram.handlers.start.link_gift_on_start",
                new_callable=AsyncMock,
                return_value=GiftRefusal.NOT_A_NEWCOMER,
            ),
        ):
            await cmd_start(
                message,
                SimpleNamespace(args="gift_abc12345"),
                AsyncMock(),
                AsyncMock(),
            )

        said = [call.args[0] for call in message.answer.await_args_list]
        assert "кого в боте ещё нет" in said[0]  # сначала про подарок
        assert "Главное меню" in said[1]  # и только потом меню

    async def test_a_good_code_says_nothing_and_waits_for_the_onboarding(self) -> None:
        """На входе подарок только обещан: активирует его конец регистрации."""
        from astra.telegram.handlers.start import cmd_start

        message = _start_message()
        state = AsyncMock()

        with (
            patch(
                "astra.telegram.handlers.start.users_crud.get_user_by_telegram_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "astra.telegram.handlers.start.users_crud.create_user",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(
                    id=1,
                    onboarding_completed=False,
                    profile=None,
                ),
            ),
            patch("astra.telegram.handlers.start.register_daily_activity", new_callable=AsyncMock),
            patch(
                "astra.telegram.handlers.start.link_gift_on_start",
                new_callable=AsyncMock,
                return_value="abc12345",
            ),
            patch(
                "astra.telegram.handlers.start._get_cached_welcome_video_file_id",
                new_callable=AsyncMock,
                return_value="cached",
            ),
        ):
            await cmd_start(
                message,
                SimpleNamespace(args="gift_abc12345"),
                state,
                AsyncMock(),
            )

        message.answer.assert_not_awaited()  # ни одного лишнего слова до приветствия
        assert state.update_data.await_args.kwargs["gift_code"] == "abc12345"
