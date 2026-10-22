"""Страховка оплаты Колеса: деньги не теряются, когда обработчик падает.

Живая база и настоящие модели. Подменён только Telegram (бот, отправка,
анимация) и точка, в которой мы роняем код. Обработчик идёт через боевой
`DbSessionMiddleware`, поэтому видно то, что видит человек: исключение не
долетает, бронь снята, платёж возвращён.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from aiogram.types import Message
from sqlalchemy import func, select

from astra.core.observability import Event
from astra.payments.models import Payment, Product
from astra.payments.service import ProductPriceInfo, wheel_spin_invoice_payload
from astra.telegram.handlers import wheel
from astra.telegram.middlewares import DbSessionMiddleware
from astra.users import crud as users_crud
from astra.wallet import crud as wallet_crud
from astra.wallet.models import WalletReason
from astra.wheel import crud as wheel_crud
from astra.wheel.models import WheelPrize, WheelWin

from conftest import new_test_telegram_id

pytestmark = pytest.mark.asyncio

_WHEEL = "astra.telegram.handlers.wheel"
_GUARD = "astra.telegram.payment_guard"
PRICE = ProductPriceInfo("XTR", 5)


@pytest.fixture
async def wheel_pool(session_factory) -> AsyncIterator[None]:
    """Хотя бы один активный сектор: на пустой базе (CI) досеиваем свой."""
    async with session_factory() as session:
        if await wheel_crud.list_active_prizes(session):
            yield
            return
        code = f"guard_test_{uuid4().hex[:8]}"
        session.add(Product(code=code, kind="tarot", title="Тест"))
        await session.flush()
        prize = WheelPrize(product_code=code, discount_percent=100, weight=10)
        session.add(prize)
        await session.commit()
        prize_id = prize.id
    try:
        yield
    finally:
        async with session_factory() as session:
            await session.execute(WheelPrize.__table__.delete().where(WheelPrize.id == prize_id))
            await session.execute(Product.__table__.delete().where(Product.code == code))
            await session.commit()


@pytest.fixture
async def person(session_factory, purge_test_users, wheel_pool):
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
            birth_date=None,
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
    message.from_user = MagicMock(id=telegram_id)
    message.successful_payment = MagicMock(
        invoice_payload=payload,
        total_amount=2,
        currency="XTR",
        telegram_payment_charge_id=charge_id,
    )
    message.bot = MagicMock(refund_star_payment=AsyncMock())
    return message


async def _hold_for_invoice(session_factory, user_id, payload: str) -> None:
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


async def _balance(session_factory, user_id) -> int:
    async with session_factory() as session:
        return await wallet_crud.get_balance(session, user_id)


def _patches(**overrides) -> dict:
    base = {
        f"{_WHEEL}.show_screen": AsyncMock(return_value=1),
        f"{_WHEEL}.play_spin_animation": AsyncMock(),
        f"{_GUARD}.capture_exception": MagicMock(),
        f"{_GUARD}.log": MagicMock(),
    }
    base.update(overrides)
    return base


class _Patched:
    def __init__(self, mocks: dict) -> None:
        self.mocks = mocks
        self._patchers = [patch(name, mock) for name, mock in mocks.items()]

    def __enter__(self) -> dict:
        for patcher in self._patchers:
            patcher.start()
        return self.mocks

    def __exit__(self, *exc) -> None:
        for patcher in self._patchers:
            patcher.stop()


class TestBeforeRecord:
    @pytest.mark.parametrize(
        "broken",
        ["register_wheel_spin_payment", "settle_charge", "perform_spin"],
    )
    async def test_failure_refunds_everything_and_swallows(
        self, session_factory, person, broken: str
    ) -> None:
        user_id, telegram_id = person
        payload = wheel_spin_invoice_payload(uuid4())
        charge_id = f"guard-{uuid4().hex}"
        await _hold_for_invoice(session_factory, user_id, payload)
        assert await _balance(session_factory, user_id) == 2
        message = _paid_message(telegram_id, payload, charge_id)

        mocks = _patches(**{f"{_WHEEL}.{broken}": AsyncMock(side_effect=RuntimeError("бум"))})
        with _Patched(mocks) as m:
            await _through_middleware(session_factory, wheel.wheel_spin_paid, message)

        message.bot.refund_star_payment.assert_awaited_once_with(
            user_id=telegram_id,
            telegram_payment_charge_id=charge_id,
        )
        assert message.answer.call_args.args[0] == wheel._PAYMENT_FAILED_TEXT
        m[f"{_GUARD}.capture_exception"].assert_called_once()
        assert m[f"{_GUARD}.log"].exception.call_args.args[0] == Event.PAYMENT_ORPHAN
        assert await _balance(session_factory, user_id) == 5  # бронь снята
        assert await _count(session_factory, Payment, Payment.provider_charge_id == charge_id) == 0
        assert await _count(session_factory, WheelWin, WheelWin.user_id == user_id) == 0

    async def test_failed_telegram_refund_is_reported_honestly(
        self, session_factory, person
    ) -> None:
        _, telegram_id = person
        message = _paid_message(telegram_id, wheel_spin_invoice_payload(uuid4()), "c-honest")
        message.bot.refund_star_payment = AsyncMock(side_effect=RuntimeError("telegram лёг"))
        mocks = _patches(
            **{f"{_WHEEL}.register_wheel_spin_payment": AsyncMock(side_effect=RuntimeError("x"))},
        )
        with _Patched(mocks) as m:
            await _through_middleware(session_factory, wheel.wheel_spin_paid, message)

        from astra.telegram.payment_guard import REFUND_FAILED_TEXT

        assert message.answer.call_args.args[0] == REFUND_FAILED_TEXT
        events = [c.args[0] for c in m[f"{_GUARD}.log"].exception.call_args_list]
        assert Event.PAYMENT_REFUND_FAILED in events


class TestAfterRecord:
    async def test_animation_failure_keeps_money_and_sends_prize_as_text(
        self, session_factory, person
    ) -> None:
        user_id, telegram_id = person
        charge_id = f"guard-{uuid4().hex}"
        message = _paid_message(telegram_id, wheel_spin_invoice_payload(uuid4()), charge_id)
        mocks = _patches(
            **{f"{_WHEEL}.play_spin_animation": AsyncMock(side_effect=RuntimeError("анимация"))},
        )
        with _Patched(mocks) as m:
            await _through_middleware(session_factory, wheel.wheel_spin_paid, message)

        message.bot.refund_star_payment.assert_not_awaited()
        assert await _count(session_factory, Payment, Payment.provider_charge_id == charge_id) == 1
        assert await _count(session_factory, WheelWin, WheelWin.user_id == user_id) == 1
        text = message.answer.call_args.args[0]
        assert text.startswith("🎉 <b>Твой приз</b>")
        m[f"{_GUARD}.capture_exception"].assert_called_once()

    async def test_happy_path_does_not_touch_guard(self, session_factory, person) -> None:
        user_id, telegram_id = person
        message = _paid_message(telegram_id, wheel_spin_invoice_payload(uuid4()), "c-ok")
        with _Patched(_patches()) as m:
            await _through_middleware(session_factory, wheel.wheel_spin_paid, message)

        message.bot.refund_star_payment.assert_not_awaited()
        message.answer.assert_not_awaited()
        m[f"{_GUARD}.capture_exception"].assert_not_called()
        assert await _count(session_factory, WheelWin, WheelWin.user_id == user_id) == 1


class TestWalletCoveredPrice:
    async def _tap(self, session_factory, telegram_id: int, mocks: dict) -> MagicMock:
        callback = MagicMock()
        callback.answer = AsyncMock()
        callback.from_user = MagicMock(id=telegram_id)
        callback.message = MagicMock(spec=Message)
        callback.message.answer = AsyncMock()
        with _Patched(mocks):
            await _through_middleware(session_factory, wheel.cb_spin_paid, callback)
        return callback

    async def test_spin_failure_returns_stars_to_wallet(self, session_factory, person) -> None:
        user_id, telegram_id = person
        mocks = _patches(
            **{
                f"{_WHEEL}.get_wheel_spin_price": AsyncMock(return_value=PRICE),
                f"{_WHEEL}.perform_spin": AsyncMock(side_effect=RuntimeError("вращение")),
            },
        )
        callback = await self._tap(session_factory, telegram_id, mocks)

        assert callback.message.answer.call_args.args[0] == wheel._SPIN_FAILED_TEXT
        assert await _balance(session_factory, user_id) == 5  # списание откатилось
        assert await _count(session_factory, WheelWin, WheelWin.user_id == user_id) == 0

    async def test_success_spends_and_gives_prize_in_one_commit(
        self, session_factory, person
    ) -> None:
        user_id, telegram_id = person
        mocks = _patches(**{f"{_WHEEL}.get_wheel_spin_price": AsyncMock(return_value=PRICE)})
        await self._tap(session_factory, telegram_id, mocks)

        assert await _balance(session_factory, user_id) == 0
        assert await _count(session_factory, WheelWin, WheelWin.user_id == user_id) == 1

    async def test_animation_failure_after_commit_keeps_prize_as_text(
        self, session_factory, person
    ) -> None:
        user_id, telegram_id = person
        mocks = _patches(
            **{
                f"{_WHEEL}.get_wheel_spin_price": AsyncMock(return_value=PRICE),
                f"{_WHEEL}.play_spin_animation": AsyncMock(side_effect=RuntimeError("анимация")),
            },
        )
        callback = await self._tap(session_factory, telegram_id, mocks)

        assert await _balance(session_factory, user_id) == 0
        assert callback.message.answer.call_args.args[0].startswith("🎉 <b>Твой приз</b>")
