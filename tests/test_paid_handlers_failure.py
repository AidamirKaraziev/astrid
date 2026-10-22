"""Оплата таро и «Спроси Астрид» не теряется, когда обработчик падает.

Живая база и настоящие модели. Подменён только Telegram и точка, где мы роняем
код. Обработчик идёт через боевой `DbSessionMiddleware`, поэтому видно то, что
видит человек: исключение не долетает, бронь снята, платёж возвращён (до записи)
или остался (после записи), а задача в воркер уходит раньше оформления.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from aiogram.types import Message
from pydantic import BaseModel
from sqlalchemy import func, select

from astra.ask import models as ask_crud
from astra.core.observability import Event
from astra.payments.models import Payment
from astra.payments.service import ProductPriceInfo, ask_invoice_payload, tarot_invoice_payload
from astra.services.ask_service import ASK_FAILED_REFUNDED_TEXT, ASK_FAILED_TEXT
from astra.services.tarot_reading_service import (
    READING_FAILED_REFUNDED_TEXT,
    create_reading_draft,
)
from astra.services.wallet_service import Charge
from astra.tarot.enums import ReadingStatus
from astra.tarot.models import TarotReading
from astra.tarot.spreads import SpreadType
from astra.telegram import ask_text as A
from astra.telegram.handlers import ask_astrid, tarot_spreads
from astra.telegram.middlewares import DbSessionMiddleware
from astra.telegram.payment_guard import REFUND_FAILED_TEXT
from astra.users import crud as users_crud
from astra.wallet import crud as wallet_crud
from astra.wallet.models import WalletReason

from conftest import new_test_telegram_id

pytestmark = pytest.mark.asyncio

_TAROT = "astra.telegram.handlers.tarot_spreads"
_ASK = "astra.telegram.handlers.ask_astrid"
_GUARD = "astra.telegram.payment_guard"
QUESTION = "love_fated_count"


class _Computed(BaseModel):
    methodology_version: int = 1


@pytest.fixture
async def person(session_factory, purge_test_users):
    """Пользователь с профилем и 5 ⭐ на счёте, закоммиченный в базу."""
    async with session_factory() as session:
        user = await users_crud.create_user(
            session,
            telegram_id=new_test_telegram_id(),
            username=None,
            language_code="ru",
        )
        await users_crud.create_profile(
            session,
            user_id=user.id,
            display_name="Тест",
            birth_date=date(1990, 1, 1),
            birth_place_id=None,
            birth_place="Москва",
            city="Москва",
            timezone="Europe/Moscow",
        )
        user.onboarding_completed = True
        await wallet_crud.add_entry(session, user.id, 5, WalletReason.REFERRAL_REWARD)
        await session.commit()
        return user.id, user.telegram_id


def _paid_message(telegram_id: int, payload: str, charge_id: str) -> MagicMock:
    message = MagicMock(spec=Message)
    message.answer = AsyncMock()
    message.chat = MagicMock(do=AsyncMock())
    message.from_user = MagicMock(id=telegram_id)
    message.successful_payment = MagicMock(
        invoice_payload=payload,
        total_amount=2,
        currency="XTR",
        telegram_payment_charge_id=charge_id,
    )
    message.bot = MagicMock(refund_star_payment=AsyncMock())
    return message


async def _hold(session_factory, user_id: UUID, payload: str) -> None:
    """Как при показе инвойса: на 5 ⭐ цены 3 ⭐ забронированы со счёта, 2 ⭐ — инвойс."""
    async with session_factory() as session:
        await wallet_crud.hold(session, user_id, 3, payload=payload)
        await session.commit()


async def _through_middleware(session_factory, handler, *args) -> None:
    async def call(event, data) -> None:
        await handler(*args, data["session"])

    await DbSessionMiddleware(session_factory)(call, MagicMock(), {})


async def _count(session_factory, model, *where) -> int:
    async with session_factory() as session:
        stmt = select(func.count()).select_from(model).where(*where)
        return (await session.execute(stmt)).scalar_one()


async def _balance(session_factory, user_id: UUID) -> int:
    async with session_factory() as session:
        return await wallet_crud.get_balance(session, user_id)


class _Patched:
    def __init__(self, mocks: dict[str, object]) -> None:
        self._patchers = [patch(name, mock) for name, mock in mocks.items()]

    def __enter__(self) -> None:
        for patcher in self._patchers:
            patcher.start()

    def __exit__(self, *exc: object) -> None:
        for patcher in self._patchers:
            patcher.stop()


def _guard_mocks() -> dict[str, object]:
    return {f"{_GUARD}.capture_exception": MagicMock(), f"{_GUARD}.log": MagicMock()}


def _texts(message: MagicMock) -> list[str]:
    return [c.args[0] for c in message.answer.call_args_list]


def _boom(name: str) -> AsyncMock:
    return AsyncMock(side_effect=RuntimeError(name))


# ───────────────────────────── таро ─────────────────────────────


async def _tarot_setup(session_factory, person):
    user_id, telegram_id = person
    async with session_factory() as session:
        user = await users_crud.get_user_by_id(session, user_id)
        reading = await create_reading_draft(
            session, user, SpreadType.THREE_CARDS, None, date(2026, 1, 1)
        )
        await session.commit()
        reading_id = reading.id
    payload = tarot_invoice_payload(reading_id)
    charge_id = f"tarot-{uuid4().hex}"
    await _hold(session_factory, user_id, payload)
    return reading_id, charge_id, _paid_message(telegram_id, payload, charge_id)


def _tarot_mocks(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "show_screen": AsyncMock(return_value=1),
        "_reveal_reading": AsyncMock(),
        "publish_tarot_reading_generate": AsyncMock(),
    }
    base.update(overrides)
    return {**{f"{_TAROT}.{k}": v for k, v in base.items()}, **_guard_mocks()}


class TestTarotBeforeRecord:
    @pytest.mark.parametrize(
        "broken",
        ["register_tarot_payment", "settle_charge", "mark_reading_paid", "record_usage"],
    )
    async def test_failure_refunds_everything_and_says_it_once(
        self, session_factory, person, broken: str
    ) -> None:
        user_id, telegram_id = person
        _, charge_id, message = await _tarot_setup(session_factory, person)
        mocks = _tarot_mocks(**{broken: _boom(broken)})
        with _Patched(mocks):
            await _through_middleware(session_factory, tarot_spreads.spread_paid, message)

        message.bot.refund_star_payment.assert_awaited_once_with(
            user_id=telegram_id, telegram_payment_charge_id=charge_id
        )
        assert _texts(message) == [READING_FAILED_REFUNDED_TEXT]  # ровно одно сообщение
        mocks[f"{_TAROT}.publish_tarot_reading_generate"].assert_not_awaited()
        assert await _balance(session_factory, user_id) == 5  # бронь снята
        assert await _count(session_factory, Payment, Payment.provider_charge_id == charge_id) == 0
        assert mocks[f"{_GUARD}.log"].exception.call_args.args[0] == Event.PAYMENT_ORPHAN


class TestTarotAfterRecord:
    @pytest.mark.parametrize("broken", ["show_screen", "_reveal_reading"])
    async def test_screen_failure_keeps_money_and_publishes_first(
        self, session_factory, person, broken: str
    ) -> None:
        reading_id, charge_id, message = await _tarot_setup(session_factory, person)
        mocks = _tarot_mocks(**{broken: _boom(broken)})
        with _Patched(mocks):
            await _through_middleware(session_factory, tarot_spreads.spread_paid, message)

        message.bot.refund_star_payment.assert_not_awaited()
        mocks[f"{_TAROT}.publish_tarot_reading_generate"].assert_awaited_once_with(reading_id)
        assert await _count(session_factory, Payment, Payment.provider_charge_id == charge_id) == 1
        async with session_factory() as session:
            reading = await session.get(TarotReading, reading_id)
            assert reading is not None
            assert reading.status != ReadingStatus.PENDING_PAYMENT
        assert _texts(message) == [tarot_spreads._PAID_THANKS_TEXT]  # одно сообщение
        mocks[f"{_GUARD}.capture_exception"].assert_called_once()

    async def test_publish_goes_before_screen(self, session_factory, person) -> None:
        _, _, message = await _tarot_setup(session_factory, person)
        order = MagicMock()
        order.publish, order.screen, order.reveal = AsyncMock(), AsyncMock(), AsyncMock()
        mocks = _tarot_mocks(
            publish_tarot_reading_generate=order.publish,
            show_screen=order.screen,
            _reveal_reading=order.reveal,
        )
        with _Patched(mocks):
            await _through_middleware(session_factory, tarot_spreads.spread_paid, message)

        assert [c[0] for c in order.mock_calls] == ["publish", "screen", "reveal"]


class TestTarotCoveredByWallet:
    """Счёт закрыл всю цену: платежа Telegram нет, порядок тот же."""

    async def _run(self, **overrides: object) -> AsyncMock:
        reading = MagicMock(id=uuid4(), spread_type="three_cards")
        reading.cards = []
        message = MagicMock()
        message.text = "Вопрос про работу и деньги"
        message.from_user = MagicMock(id=1)
        message.answer = AsyncMock()
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"tarot_spread_type": "three_cards"})
        user = MagicMock(id=uuid4(), onboarding_completed=True)
        user.profile = MagicMock(timezone="Europe/Moscow")
        user.last_active_date = None
        user.streak_current = user.streak_best = user.points = 0
        publish = AsyncMock()
        base: dict[str, object] = {
            "users_crud.get_user_by_telegram_id": AsyncMock(return_value=user),
            "try_acquire_reading_lock": AsyncMock(return_value=True),
            "release_reading_lock": AsyncMock(),
            "create_reading_draft": AsyncMock(return_value=reading),
            "get_tarot_price": AsyncMock(return_value=ProductPriceInfo("XTR", 3)),
            "_wheel_win_for_spread": AsyncMock(return_value=None),
            "plan_charge": AsyncMock(
                return_value=Charge(ProductPriceInfo("XTR", 3), from_wallet=3, to_invoice=0)
            ),
            "settle_charge": AsyncMock(return_value=3),
            "mark_reading_paid": AsyncMock(),
            "record_usage": AsyncMock(),
            "publish_tarot_reading_generate": publish,
            "show_screen": AsyncMock(return_value=1),
            "_reveal_reading": AsyncMock(),
            "close_screen": AsyncMock(),
            "react": AsyncMock(),
        }
        base.update(overrides)
        with _Patched({f"{_TAROT}.{k}": v for k, v in base.items()}):
            try:
                await tarot_spreads.spread_question(message, state, AsyncMock())
            except RuntimeError:
                pass  # оформление упало; нас интересует, ушла ли задача
        return publish

    @pytest.mark.parametrize("broken", ["show_screen", "_reveal_reading"])
    async def test_screen_failure_does_not_cancel_publish(self, broken: str) -> None:
        publish = await self._run(**{broken: _boom(broken)})
        publish.assert_awaited_once()

    async def test_publish_goes_before_screen(self) -> None:
        order = MagicMock()
        order.publish, order.screen = AsyncMock(), AsyncMock(return_value=1)
        await self._run(publish_tarot_reading_generate=order.publish, show_screen=order.screen)
        assert [c[0] for c in order.mock_calls][:2] == ["publish", "screen"]


# ───────────────────────────── «Спроси» ─────────────────────────────


async def _ask_setup(session_factory, person):
    user_id, telegram_id = person
    async with session_factory() as session:
        reading = await ask_crud.create_draft(
            session,
            user_id=user_id,
            question_key=QUESTION,
            in_relationship=True,
            context={"in_relationship": True},
        )
        await session.commit()
        reading_id = reading.id
    payload = ask_invoice_payload(reading_id)
    charge_id = f"ask-{uuid4().hex}"
    await _hold(session_factory, user_id, payload)
    return reading_id, charge_id, _paid_message(telegram_id, payload, charge_id)


def _ask_mocks(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "compute_for_reading": AsyncMock(return_value=_Computed()),
        "_send_card": AsyncMock(),
        "publish_ask_answer_generate": AsyncMock(),
    }
    base.update(overrides)
    return {**{f"{_ASK}.{k}": v for k, v in base.items()}, **_guard_mocks()}


class TestAskBeforeRecord:
    @pytest.mark.parametrize(
        "target",
        ["register_ask_payment", "settle_charge", "ask_crud.mark_paid", "record_usage"],
    )
    async def test_failure_refunds_everything_and_says_it_once(
        self, session_factory, person, target: str
    ) -> None:
        user_id, telegram_id = person
        _, charge_id, message = await _ask_setup(session_factory, person)
        mocks = _ask_mocks(**{target: _boom(target)})
        with _Patched(mocks):
            await _through_middleware(session_factory, ask_astrid.ask_paid, message)

        message.bot.refund_star_payment.assert_awaited_once_with(
            user_id=telegram_id, telegram_payment_charge_id=charge_id
        )
        texts = _texts(message)
        assert texts.count(ASK_FAILED_REFUNDED_TEXT) == 1
        assert not {ASK_FAILED_TEXT, REFUND_FAILED_TEXT} & set(texts)  # второго сообщения нет
        mocks[f"{_ASK}.publish_ask_answer_generate"].assert_not_awaited()
        assert await _balance(session_factory, user_id) == 5
        assert await _count(session_factory, Payment, Payment.provider_charge_id == charge_id) == 0
        assert mocks[f"{_GUARD}.log"].exception.call_args.args[0] == Event.PAYMENT_ORPHAN


class TestAskAfterRecord:
    @pytest.mark.parametrize("broken", ["_send_card", "answer"])
    async def test_delivery_failure_keeps_money_and_publishes_first(
        self, session_factory, person, broken: str
    ) -> None:
        reading_id, charge_id, message = await _ask_setup(session_factory, person)
        overrides: dict[str, object] = {}
        if broken == "_send_card":
            overrides["_send_card"] = _boom("card")
        else:

            async def answer(text: str, **kwargs: object) -> None:
                if text == A.ASK_ANSWER_COMING_TEXT:
                    raise RuntimeError("answer")

            message.answer = AsyncMock(side_effect=answer)
        mocks = _ask_mocks(**overrides)
        with _Patched(mocks):
            await _through_middleware(session_factory, ask_astrid.ask_paid, message)

        message.bot.refund_star_payment.assert_not_awaited()
        mocks[f"{_ASK}.publish_ask_answer_generate"].assert_awaited_once_with(reading_id)
        assert await _count(session_factory, Payment, Payment.provider_charge_id == charge_id) == 1
        async with session_factory() as session:
            reading = await ask_crud.get_reading(session, reading_id)
            assert reading is not None
            assert reading.charge_id == charge_id
        mocks[f"{_GUARD}.capture_exception"].assert_called()

    async def test_publish_goes_before_card_and_answer(self, session_factory, person) -> None:
        _, _, message = await _ask_setup(session_factory, person)
        order = MagicMock()
        order.publish, order.card = AsyncMock(), AsyncMock()
        mocks = _ask_mocks(publish_ask_answer_generate=order.publish, _send_card=order.card)
        with _Patched(mocks):
            await _through_middleware(session_factory, ask_astrid.ask_paid, message)

        assert [c[0] for c in order.mock_calls] == ["publish", "card"]
        assert _texts(message)[-1] == A.ASK_ANSWER_COMING_TEXT
