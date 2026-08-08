"""Колесо фортуны: вращения, анимация, оплата, активация приза в раскладе."""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from aiogram.types import Message

from astra.payments.service import (
    ProductPriceInfo,
    parse_tarot_invoice_payload,
    parse_wheel_spin_invoice_payload,
    wheel_spin_invoice_payload,
)
from astra.telegram.handlers.tarot_spreads import spread_question
from astra.telegram.handlers.wheel import (
    cb_activate_prize,
    cb_spin_free,
    cb_spin_paid,
    wheel_spin_paid,
)
from astra.telegram.wheel_animation import (
    build_frames,
    frame_offsets,
    play_spin_animation,
    render_frame,
)
from astra.wheel.enums import SpinType

_WHEEL = "astra.telegram.handlers.wheel"
_TAROT = "astra.telegram.handlers.tarot_spreads"


def _user() -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.telegram_id = 100500
    user.onboarding_completed = True
    user.profile = MagicMock(timezone="Europe/Moscow")
    # серия и очки: любое использование продукта двигает их (usage.record_usage)
    user.last_active_date = None
    user.streak_current = 0
    user.streak_best = 0
    user.points = 0
    return user


def _prize(code: str = "tarot_wish", discount: int = 100) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        product_code=code,
        discount_percent=discount,
        weight=10,
    )


def _win(user_id, *, code: str = "tarot_wish", discount: int = 100, **kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        id=kwargs.get("id", uuid4()),
        user_id=user_id,
        prize_id=kwargs.get("prize_id", uuid4()),
        product_code=code,
        discount_percent=discount,
        expires_at=kwargs.get("expires_at"),
        activated_at=kwargs.get("activated_at"),
    )


def _bot_message() -> MagicMock:
    """Мок Message со спекой: хендлеры колеса проверяют isinstance(..., Message)."""
    message = MagicMock(spec=Message)
    message.answer = AsyncMock()
    message.answer_invoice = AsyncMock()
    return message


def _callback() -> MagicMock:
    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.from_user = MagicMock(id=100500)
    callback.message = _bot_message()
    return callback


def _wheel_mocks(**overrides) -> dict:
    prize = overrides.pop("_prize", _prize())
    defaults = {
        "users_crud.get_user_by_telegram_id": AsyncMock(return_value=_user()),
        "wheel_crud.has_free_win_on": AsyncMock(return_value=False),
        "wheel_crud.list_active_prizes": AsyncMock(return_value=[prize]),
        "perform_spin": AsyncMock(),
        "play_spin_animation": AsyncMock(),
        "get_wheel_spin_price": AsyncMock(return_value=ProductPriceInfo("XTR", 5)),
        # Раздел живёт в одном редактируемом экране: хаб, вращение, приз.
        "show_screen": AsyncMock(return_value=888),
        "close_screen": AsyncMock(),
    }
    defaults.update(overrides)
    return defaults


def _wheel_screen_text(mocks: dict) -> str:
    call = mocks["show_screen"].call_args
    assert call is not None, "экран колеса не обновлялся"
    return str(call.args[1])


async def _run_wheel(handler, mocks: dict, *args) -> None:
    with ExitStack() as stack:
        for name, mock in mocks.items():
            stack.enter_context(patch(f"{_WHEEL}.{name}", mock))
        await handler(*args)


class TestAnimation:
    def test_last_frame_stops_on_winner(self) -> None:
        labels = ["🌟 A", "🃏 B", "💕 C", "🎁 D"]
        frames = build_frames(labels, winner_index=2)
        assert frames[-1].count("▸") == 1
        pointer_line = [ln for ln in frames[-1].splitlines() if ln.startswith("▸")][0]
        assert "💕 C" in pointer_line

    def test_reel_moves_between_frames(self) -> None:
        offsets = frame_offsets(total=5, winner_index=0)
        assert offsets[-1] == 0
        assert len(set(offsets)) > 1  # лента реально прокручивается

    def test_short_pool_renders_without_crash(self) -> None:
        assert "▸ 🌟 A" in render_frame(["🌟 A"], 0)
        assert render_frame(["🌟 A", "🃏 B"], 1).count("\n") >= 2
        assert len(build_frames(["🌟 A"], 0)) == 1  # крутить нечего

    @pytest.mark.parametrize("total", [2, 3, 4, 5, 6, 7, 8])
    def test_neighbouring_frames_always_differ(self, total: int) -> None:
        # Одинаковый текст подряд Telegram редактировать откажется и анимация оборвётся.
        # Особый случай — пул из 3 призов при шаге ленты 3.
        for winner in range(total):
            offsets = frame_offsets(total, winner)
            assert offsets[-1] == winner
            assert all(a != b for a, b in zip(offsets, offsets[1:], strict=False))

            labels = [f"приз {i}" for i in range(total)]
            frames = build_frames(labels, winner)
            assert all(a != b for a, b in zip(frames, frames[1:], strict=False))

    async def test_animation_spins_inside_the_screen(self) -> None:
        """Лента крутится в экране раздела: отдельного сообщения не появляется.

        Раньше анимация слала своё сообщение, и последний кадр «Колесо
        крутится…» навсегда оставался в чате рядом с карточкой приза.
        """
        message = _bot_message()
        screen = AsyncMock(return_value=888)

        with (
            patch("astra.telegram.wheel_animation.show_screen", screen),
            patch("astra.telegram.wheel_animation.asyncio.sleep", AsyncMock()),
        ):
            await play_spin_animation(message, ["🌟 A", "🃏 B", "💕 C"], 1, scope="wheel")

        message.answer.assert_not_called()
        assert screen.await_count == len(build_frames(["🌟 A", "🃏 B", "💕 C"], 1))
        assert all(c.kwargs["scope"] == "wheel" for c in screen.call_args_list)
        assert "💕 C" in str(screen.call_args_list[-1].args[1])  # финал на победителе


class TestFreeSpin:
    async def test_free_spin_gives_prize_and_animates(self) -> None:
        user = _user()
        prize = _prize()
        win = _win(user.id, prize_id=prize.id)
        session = AsyncMock()
        callback = _callback()
        mocks = _wheel_mocks(
            _prize=prize,
            **{"users_crud.get_user_by_telegram_id": AsyncMock(return_value=user)},
            perform_spin=AsyncMock(return_value=win),
        )

        await _run_wheel(cb_spin_free, mocks, callback, session)

        assert mocks["perform_spin"].await_args.args[2] is SpinType.FREE
        session.commit.assert_awaited_once()
        mocks["play_spin_animation"].assert_awaited_once()
        # Карточка приза — финальный кадр того же экрана, а не новое сообщение.
        callback.message.answer.assert_not_called()
        card = _wheel_screen_text(mocks)
        assert "Загадай желание" in card and "бесплатно" in card

    async def test_second_free_spin_same_day_refused(self) -> None:
        callback = _callback()
        mocks = _wheel_mocks(**{"wheel_crud.has_free_win_on": AsyncMock(return_value=True)})

        await _run_wheel(cb_spin_free, mocks, callback, AsyncMock())

        mocks["perform_spin"].assert_not_awaited()
        # Отказ живёт в плашке сверху, а не сообщением в чате.
        callback.message.answer.assert_not_called()
        assert "завтра" in callback.answer.call_args.args[0]

    async def test_double_tap_race_is_caught(self) -> None:
        session = AsyncMock()
        callback = _callback()
        mocks = _wheel_mocks(perform_spin=AsyncMock(side_effect=IntegrityError("x", "y", Exception())))

        await _run_wheel(cb_spin_free, mocks, callback, session)

        session.rollback.assert_awaited_once()
        assert "завтра" in callback.message.answer.call_args.args[0]

    async def test_empty_pool_reports_pause(self) -> None:
        """Пул опустел между проверкой и вращением: callback уже отвечен, остаётся сообщение."""
        callback = _callback()
        mocks = _wheel_mocks(perform_spin=AsyncMock(return_value=None))

        await _run_wheel(cb_spin_free, mocks, callback, AsyncMock())

        assert "паузе" in callback.message.answer.call_args.args[0]

    async def test_known_empty_pool_reports_pause_in_alert(self) -> None:
        """Призов нет с самого начала — колесо не крутится, чат не засоряется."""
        callback = _callback()
        mocks = _wheel_mocks(**{"wheel_crud.list_active_prizes": AsyncMock(return_value=[])})

        await _run_wheel(cb_spin_free, mocks, callback, AsyncMock())

        mocks["perform_spin"].assert_not_awaited()
        callback.message.answer.assert_not_called()
        assert "паузе" in callback.answer.call_args.args[0]
        assert callback.answer.call_args.kwargs["show_alert"] is True


class TestPaidSpin:
    async def test_paid_spin_sends_invoice_with_wheel_payload(self) -> None:
        callback = _callback()
        mocks = _wheel_mocks()

        await _run_wheel(cb_spin_paid, mocks, callback, AsyncMock())

        invoice = callback.message.answer_invoice.call_args.kwargs
        assert invoice["currency"] == "XTR"
        assert invoice["prices"][0].amount == 5
        assert invoice["payload"].startswith("wheel_spin:")
        mocks["perform_spin"].assert_not_awaited()  # крутим только после оплаты

    async def test_free_priced_spin_skips_invoice(self) -> None:
        callback = _callback()
        win = _win(uuid4())
        mocks = _wheel_mocks(
            get_wheel_spin_price=AsyncMock(return_value=ProductPriceInfo("XTR", 5, 100)),
            perform_spin=AsyncMock(return_value=win),
        )

        await _run_wheel(cb_spin_paid, mocks, callback, AsyncMock())

        callback.message.answer_invoice.assert_not_awaited()
        assert mocks["perform_spin"].await_args.args[2] is SpinType.PAID


class TestPaymentSpin:
    def _paid_message(self, payload: str) -> MagicMock:
        message = _bot_message()
        message.from_user = MagicMock(id=100500)
        message.successful_payment = MagicMock(
            invoice_payload=payload,
            total_amount=5,
            currency="XTR",
            telegram_payment_charge_id="charge-1",
        )
        message.bot = MagicMock(refund_star_payment=AsyncMock())
        return message

    async def test_payment_spins_wheel_and_links_payment(self) -> None:
        user = _user()
        payment = MagicMock(id=uuid4())
        win = _win(user.id)
        message = self._paid_message(wheel_spin_invoice_payload(uuid4()))
        session = AsyncMock()
        mocks = _wheel_mocks(
            **{"users_crud.get_user_by_telegram_id": AsyncMock(return_value=user)},
            register_wheel_spin_payment=AsyncMock(return_value=payment),
            perform_spin=AsyncMock(return_value=win),
        )

        await _run_wheel(wheel_spin_paid, mocks, message, session)

        assert mocks["perform_spin"].await_args.kwargs["payment_id"] == payment.id
        assert mocks["perform_spin"].await_args.args[2] is SpinType.PAID
        message.bot.refund_star_payment.assert_not_awaited()

    async def test_duplicate_payment_does_not_spin_twice(self) -> None:
        message = self._paid_message(wheel_spin_invoice_payload(uuid4()))
        mocks = _wheel_mocks(register_wheel_spin_payment=AsyncMock(return_value=None))

        await _run_wheel(wheel_spin_paid, mocks, message, AsyncMock())

        mocks["perform_spin"].assert_not_awaited()

    async def test_empty_pool_after_payment_refunds_stars(self) -> None:
        message = self._paid_message(wheel_spin_invoice_payload(uuid4()))
        session = AsyncMock()
        mocks = _wheel_mocks(
            register_wheel_spin_payment=AsyncMock(return_value=MagicMock(id=uuid4())),
            perform_spin=AsyncMock(return_value=None),
        )

        await _run_wheel(wheel_spin_paid, mocks, message, session)

        session.rollback.assert_awaited_once()
        message.bot.refund_star_payment.assert_awaited_once()
        assert "вернулись" in message.answer.call_args.args[0]


class TestPrizeActivation:
    async def test_activation_starts_matching_spread(self) -> None:
        user = _user()
        win = _win(user.id, code="tarot_three_cards", discount=50)
        callback = _callback()
        callback.data = f"wheel:use:{win.id}"
        state = AsyncMock()
        mocks = _wheel_mocks(
            **{"users_crud.get_user_by_telegram_id": AsyncMock(return_value=user)},
            **{"wheel_crud.get_win": AsyncMock(return_value=win)},
            start_spread_with_prize=AsyncMock(),
        )

        await _run_wheel(cb_activate_prize, mocks, callback, state, AsyncMock())

        args = mocks["start_spread_with_prize"].await_args.args
        assert str(args[3]) == "three_cards"
        assert args[4] == win.id
        assert args[5] is user  # пользователя передаём явно, см. тест ниже

    async def test_activation_does_not_look_user_up_by_bot_message(self) -> None:
        """Регрессия: сообщение под кнопкой принадлежит боту, а не игроку.

        Раньше расклад искал пользователя по callback.message.from_user (это бот)
        и отвечал «Сначала пройди регистрацию: /start» вместо запроса вопроса.
        """
        user = _user()
        win = _win(user.id, code="tarot_wish", discount=100)
        bot_id = 777_000_777
        callback = _callback()
        callback.data = f"wheel:use:{win.id}"
        callback.message.from_user = MagicMock(id=bot_id, is_bot=True)  # сообщение бота

        # users_crud — общий модуль для обоих хендлеров, поэтому различаем по id:
        # игрок есть в базе, бот — нет.
        async def lookup(_session, telegram_id):
            return user if telegram_id == user.telegram_id else None

        wheel_mocks = _wheel_mocks(
            **{"users_crud.get_user_by_telegram_id": AsyncMock(side_effect=lookup)},
            **{"wheel_crud.get_win": AsyncMock(return_value=win)},
        )
        # start_spread_with_prize не мокаем — проверяем реальный путь до таро.
        # Экран таро подменяем: настоящий пошёл бы в Bot API мимо мока сообщения.
        screen = AsyncMock(return_value=777)
        with patch(f"{_TAROT}.show_screen", screen):
            await _run_wheel(cb_activate_prize, wheel_mocks, callback, AsyncMock(), AsyncMock())

        wheel_mocks["close_screen"].assert_awaited_once()  # экран колеса погас
        shown = [str(c.args[1]) for c in screen.call_args_list]
        answers = [str(c.args[0]) for c in callback.message.answer.call_args_list]
        assert not any("регистрацию" in text for text in answers + shown), answers + shown
        assert any("Загадай желание" in text for text in shown), shown

    async def test_burned_prize_is_refused(self) -> None:
        user = _user()
        burned = _win(user.id, activated_at=MagicMock())
        callback = _callback()
        callback.data = f"wheel:use:{burned.id}"
        mocks = _wheel_mocks(
            **{"users_crud.get_user_by_telegram_id": AsyncMock(return_value=user)},
            **{"wheel_crud.get_win": AsyncMock(return_value=burned)},
            start_spread_with_prize=AsyncMock(),
        )

        await _run_wheel(cb_activate_prize, mocks, callback, AsyncMock(), AsyncMock())

        mocks["start_spread_with_prize"].assert_not_awaited()
        callback.message.answer.assert_not_called()
        assert "сгорел" in callback.answer.call_args.args[0]
        assert callback.answer.call_args.kwargs["show_alert"] is True

    async def test_foreign_prize_is_refused(self) -> None:
        callback = _callback()
        someone_else = _win(uuid4())
        callback.data = f"wheel:use:{someone_else.id}"
        mocks = _wheel_mocks(
            **{"wheel_crud.get_win": AsyncMock(return_value=someone_else)},
            start_spread_with_prize=AsyncMock(),
        )

        await _run_wheel(cb_activate_prize, mocks, callback, AsyncMock(), AsyncMock())

        mocks["start_spread_with_prize"].assert_not_awaited()


class TestPrizeAppliedToSpread:
    """Приз доезжает до цены расклада — это ради него всё и затевалось."""

    def _message(self, text: str) -> MagicMock:
        message = MagicMock()
        message.text = text
        message.from_user = MagicMock(id=100500)
        message.answer = AsyncMock()
        message.answer_invoice = AsyncMock()
        return message

    def _state(self, data: dict) -> AsyncMock:
        state = AsyncMock()
        state.get_data = AsyncMock(return_value=data)
        return state

    def _tarot_mocks(self, user, win, **overrides) -> dict:
        reading = MagicMock(id=uuid4(), spread_type="wish")
        reading.cards = [
            {"position": 1, "position_key": "heart", "card_id": "cups_06", "reversed": False},
            {"position": 2, "position_key": "path", "card_id": "swords_03", "reversed": False},
            {"position": 3, "position_key": "outcome", "card_id": "major_06", "reversed": False},
        ]
        defaults = {
            "users_crud.get_user_by_telegram_id": AsyncMock(return_value=user),
            "try_acquire_reading_lock": AsyncMock(return_value=True),
            "release_reading_lock": AsyncMock(),
            "create_reading_draft": AsyncMock(return_value=reading),
            "get_tarot_price": AsyncMock(return_value=ProductPriceInfo("XTR", 50)),
            "send_card_photo": AsyncMock(),
            "send_cards_album": AsyncMock(),
            "publish_tarot_reading_generate": AsyncMock(),
            "mark_reading_paid": AsyncMock(),
            "wheel_crud.get_win": AsyncMock(return_value=win),
            "wheel_crud.get_pending_win_for_reading": AsyncMock(return_value=None),
            "reserve_win_for_reading": AsyncMock(),
            "mark_win_activated": AsyncMock(),
            # Раздел таро живёт в одном редактируемом экране.
            "show_screen": AsyncMock(return_value=777),
            "close_screen": AsyncMock(),
        }
        defaults.update(overrides)
        return defaults

    async def _run(self, mocks, message, state, session) -> None:
        with ExitStack() as stack:
            for name, mock in mocks.items():
                stack.enter_context(patch(f"{_TAROT}.{name}", mock))
            await spread_question(message, state, session)

    async def test_free_prize_skips_invoice_and_spends_prize(self) -> None:
        user = _user()
        win = _win(user.id, code="tarot_wish", discount=100)
        message = self._message("Вернётся ли он?")
        state = self._state({"tarot_spread_type": "wish", "wheel_win_id": str(win.id)})
        mocks = self._tarot_mocks(user, win)

        await self._run(mocks, message, state, AsyncMock())

        message.answer_invoice.assert_not_awaited()
        assert mocks["mark_reading_paid"].await_args.args[2] == 0
        mocks["mark_win_activated"].assert_awaited_once()  # приз потрачен
        mocks["send_cards_album"].assert_awaited_once()

    async def test_discount_prize_halves_invoice_and_reserves_prize(self) -> None:
        user = _user()
        win = _win(user.id, code="tarot_wish", discount=50)
        message = self._message("Вернётся ли он?")
        state = self._state({"tarot_spread_type": "wish", "wheel_win_id": str(win.id)})
        mocks = self._tarot_mocks(user, win)

        await self._run(mocks, message, state, AsyncMock())

        invoice = message.answer_invoice.call_args.kwargs
        assert invoice["prices"][0].amount == 25  # 50 ⭐ со скидкой приза −50%
        mocks["reserve_win_for_reading"].assert_awaited_once()
        # до оплаты приз не потрачен
        mocks["mark_win_activated"].assert_not_awaited()

    async def test_prize_beats_catalog_discount(self) -> None:
        # У товара своя акция −10%, приз даёт −50%: побеждает приз, скидки не множатся
        user = _user()
        win = _win(user.id, code="tarot_wish", discount=50)
        message = self._message("Вернётся ли он?")
        state = self._state({"tarot_spread_type": "wish", "wheel_win_id": str(win.id)})
        mocks = self._tarot_mocks(
            user, win,
            get_tarot_price=AsyncMock(return_value=ProductPriceInfo("XTR", 50, 10)),
        )

        await self._run(mocks, message, state, AsyncMock())

        assert message.answer_invoice.call_args.kwargs["prices"][0].amount == 25

    async def test_expired_prize_falls_back_to_full_price(self) -> None:
        user = _user()
        message = self._message("Вернётся ли он?")
        state = self._state({"tarot_spread_type": "wish", "wheel_win_id": str(uuid4())})
        mocks = self._tarot_mocks(user, None)

        await self._run(mocks, message, state, AsyncMock())

        assert message.answer_invoice.call_args.kwargs["prices"][0].amount == 50
        # Предупреждение о сгоревшем призе — в экране над инвойсом, не сообщением.
        warned = " ".join(str(c.args[1]) for c in mocks["show_screen"].call_args_list)
        assert "сгорел" in warned

    async def test_prize_for_other_spread_is_ignored(self) -> None:
        user = _user()
        # приз на «Три карты», а запущен расклад «Загадай желание»
        win = _win(user.id, code="tarot_three_cards", discount=100)
        message = self._message("Вернётся ли он?")
        state = self._state({"tarot_spread_type": "wish", "wheel_win_id": str(win.id)})
        mocks = self._tarot_mocks(user, win)

        await self._run(mocks, message, state, AsyncMock())

        assert message.answer_invoice.call_args.kwargs["prices"][0].amount == 50
        mocks["mark_win_activated"].assert_not_awaited()


def test_payload_prefixes_do_not_collide() -> None:
    """Платежи колеса и таро не должны перехватывать друг друга."""
    wheel_payload = wheel_spin_invoice_payload(uuid4())
    assert parse_tarot_invoice_payload(wheel_payload) is None
    assert parse_wheel_spin_invoice_payload(wheel_payload) is not None
    assert parse_wheel_spin_invoice_payload(f"tarot:{uuid4()}") is None


@pytest.mark.parametrize("payload", ["", None, "wheel_spin:not-a-uuid", "чужое"])
def test_broken_wheel_payload_is_rejected(payload) -> None:
    assert parse_wheel_spin_invoice_payload(payload) is None
