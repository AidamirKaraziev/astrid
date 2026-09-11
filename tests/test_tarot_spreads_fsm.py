"""Тесты FSM платных раскладов: вход, вопрос, инвойс Stars, оплата, назад."""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from astra.payments.service import ProductPriceInfo
from astra.services.wallet_service import Charge
from astra.tarot.enums import ReadingStatus
from astra.tarot.spreads import SpreadType
from aiogram.types import Message

from astra.telegram.button_texts import (
    BTN_BACK_MENU,
    BTN_TAROT_SKIP,
    BTN_TAROT_WISH,
    CB_TAROT_CLOSE,
    CB_TAROT_QUESTION_SKIP,
    CB_TAROT_SECTION,
    CB_TAROT_SPREAD_PREFIX,
)
from astra.telegram.handlers.tarot_spreads import (
    cb_close_spreads,
    cb_open_spreads,
    cb_pick_spread,
    cb_skip_question,
    pre_checkout,
    spread_button,
    spread_paid,
    spread_question,
)
from astra.telegram.states import TarotStates

_MODULE = "astra.telegram.handlers.tarot_spreads"


def _message(text: str) -> MagicMock:
    message = MagicMock()
    message.text = text
    message.from_user = MagicMock(id=100500)
    message.answer = AsyncMock()
    message.answer_invoice = AsyncMock()
    return message


def _state(data: dict | None = None) -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=data or {})
    return state


def _user() -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.onboarding_completed = True
    user.profile = MagicMock(timezone="Europe/Moscow")
    # серия и очки: любое использование продукта двигает их (usage.record_usage)
    user.last_active_date = None
    user.streak_current = 0
    user.streak_best = 0
    user.points = 0
    return user


def _empty_wallet_charge():
    """Кошелёк по умолчанию пуст: вся цена уходит в инвойс, как было до него."""

    async def plan(session, user_id, price, **kwargs):
        return Charge(
            price,
            from_wallet=0,
            to_invoice=0 if price.is_free else price.final_amount,
        )

    return plan

def _mocks(**overrides) -> dict:
    defaults = {
        "users_crud.get_user_by_telegram_id": AsyncMock(return_value=_user()),
        "try_acquire_reading_lock": AsyncMock(return_value=True),
        "release_reading_lock": AsyncMock(),
        "create_reading_draft": AsyncMock(return_value=MagicMock(id=uuid4())),
        "get_tarot_price": AsyncMock(return_value=ProductPriceInfo("XTR", 50)),
        "send_card_photo": AsyncMock(),
        "send_cards_album": AsyncMock(),
        "publish_tarot_reading_generate": AsyncMock(),
        # По умолчанию расклад запущен без приза колеса.
        "wheel_crud.get_win": AsyncMock(return_value=None),
        "wheel_crud.get_pending_win_for_reading": AsyncMock(return_value=None),
        "reserve_win_for_reading": AsyncMock(),
        "mark_win_activated": AsyncMock(),
        # Раздел живёт в одном редактируемом экране, а не в сообщениях чата.
        "show_screen": AsyncMock(return_value=777),
        "close_screen": AsyncMock(),
        "react": AsyncMock(),
        # Кошелёк: пустой баланс, списывать нечего.
        "plan_charge": AsyncMock(side_effect=_empty_wallet_charge()),
        "settle_charge": AsyncMock(return_value=0),
        "cancel_charge": AsyncMock(return_value=0),
    }
    defaults.update(overrides)
    return defaults


def _screen_text(mocks: dict) -> str:
    """Текст, который сейчас показан в живом экране раздела."""
    call = mocks["show_screen"].call_args
    assert call is not None, "экран раздела не обновлялся"
    return str(call.args[1])


async def _run(handler, message, state, session, mocks: dict) -> None:
    with ExitStack() as stack:
        for name, mock in mocks.items():
            stack.enter_context(patch(f"{_MODULE}.{name}", mock))
        await handler(message, state, session)


class TestSpreadButton:
    async def test_sets_state_and_asks_question(self):
        message, state = _message(BTN_TAROT_WISH), _state()
        mocks = _mocks()
        await _run(spread_button, message, state, AsyncMock(), mocks)
        state.set_state.assert_awaited_once_with(TarotStates.waiting_question)
        state.update_data.assert_awaited_once_with(tarot_spread_type="wish")
        message.answer.assert_not_called()  # вопрос живёт в экране, а не в чате
        intro = _screen_text(mocks)
        assert "желание" in intro.lower()
        assert "⭐" not in intro  # цену показывает только кнопка инвойса

    async def test_requires_onboarded_user(self):
        message, state = _message(BTN_TAROT_WISH), _state()
        await _run(
            spread_button, message, state, AsyncMock(),
            _mocks(**{"users_crud.get_user_by_telegram_id": AsyncMock(return_value=None)}),
        )
        state.set_state.assert_not_awaited()
        assert "/start" in message.answer.call_args.args[0]


class TestSpreadQuestion:
    _DATA = {"tarot_spread_type": "wish"}

    async def test_back_returns_to_main_menu(self):
        message, state = _message(BTN_BACK_MENU), _state(self._DATA)
        await _run(spread_question, message, state, AsyncMock(), _mocks())
        state.clear.assert_awaited_once()
        assert "меню" in message.answer.call_args.args[0].lower()

    async def test_too_short_question_reprompts(self):
        message, state = _message("Да"), _state(self._DATA)
        mocks = _mocks()
        await _run(spread_question, message, state, AsyncMock(), mocks)
        mocks["create_reading_draft"].assert_not_awaited()
        # Замечание к вводу переписывает экран, а не падает новым сообщением.
        message.answer.assert_not_called()
        assert "символов" in _screen_text(mocks)

    async def test_skip_rejected_when_question_required(self):
        message, state = _message(BTN_TAROT_SKIP), _state(self._DATA)
        mocks = _mocks()
        await _run(spread_question, message, state, AsyncMock(), mocks)
        mocks["create_reading_draft"].assert_not_awaited()

    async def test_unknown_spread_type_resets(self):
        message, state = _message("Нормальный вопрос?"), _state({})
        mocks = _mocks()
        await _run(spread_question, message, state, AsyncMock(), mocks)
        state.clear.assert_awaited_once()
        mocks["create_reading_draft"].assert_not_awaited()

    async def test_valid_question_creates_draft_and_sends_invoice(self):
        message, state = _message("Хочу, чтобы мы с Сашей снова были вместе"), _state(self._DATA)
        session = AsyncMock()
        mocks = _mocks()
        await _run(spread_question, message, state, session, mocks)
        mocks["create_reading_draft"].assert_awaited_once()
        assert mocks["create_reading_draft"].await_args.args[2] is SpreadType.WISH
        session.commit.assert_awaited_once()  # черновик переживёт рестарт до оплаты
        message.answer_invoice.assert_awaited_once()
        invoice = message.answer_invoice.call_args.kwargs
        assert invoice["currency"] == "XTR"
        assert invoice["payload"].startswith("tarot:")
        # цена берётся из БД по товару, не из текста/конфига
        mocks["get_tarot_price"].assert_awaited_once()
        assert invoice["prices"][0].amount == 50
        # без скидки — стандартная кнопка Telegram, без кастомной клавиатуры
        assert "reply_markup" not in invoice

    async def test_free_product_skips_invoice_and_reveals_cards(self):
        message, state = _message("Хочу, чтобы мы с Сашей снова были вместе"), _state(self._DATA)
        session = AsyncMock()
        reading = MagicMock(id=uuid4(), spread_type="wish")
        reading.cards = [
            {"position": 1, "position_key": "heart", "card_id": "cups_06", "reversed": False},
            {"position": 2, "position_key": "path", "card_id": "swords_03", "reversed": False},
            {"position": 3, "position_key": "outcome", "card_id": "major_06", "reversed": False},
        ]
        mocks = _mocks(
            get_tarot_price=AsyncMock(return_value=ProductPriceInfo("XTR", 50, 100)),
            create_reading_draft=AsyncMock(return_value=reading),
            mark_reading_paid=AsyncMock(),
        )
        await _run(spread_question, message, state, session, mocks)
        # инвойса нет, расклад выдан сразу и ушёл в worker
        message.answer_invoice.assert_not_awaited()
        mocks["mark_reading_paid"].assert_awaited_once()
        assert mocks["mark_reading_paid"].await_args.args[2] == 0  # price_stars = 0
        session.commit.assert_awaited_once()
        mocks["send_cards_album"].assert_awaited_once()
        mocks["publish_tarot_reading_generate"].assert_awaited_once_with(reading.id)
        state.clear.assert_awaited_once()

    async def test_discount_shows_crossed_price_on_pay_button(self):
        message, state = _message("Хочу, чтобы мы с Сашей снова были вместе"), _state(self._DATA)
        mocks = _mocks(get_tarot_price=AsyncMock(return_value=ProductPriceInfo("XTR", 50, 90)))
        await _run(spread_question, message, state, AsyncMock(), mocks)
        invoice = message.answer_invoice.call_args.kwargs
        assert invoice["prices"][0].amount == 5  # к оплате — цена со скидкой
        button = invoice["reply_markup"].inline_keyboard[0][0]
        assert button.pay is True
        # вариант B: «5̶0̶ ⭐ → 5 ⭐ · скидка −90%»
        assert button.text == "5̶0̶ ⭐ → 5 ⭐ · скидка −90%"
        # в сообщении над инвойсом — зачёркнутая старая цена
        sent_text = _screen_text(mocks)
        assert "<s>50 ⭐</s>" in sent_text and "−90%" in sent_text
        # карты до оплаты не показываются, задача в worker не публикуется
        mocks["send_cards_album"].assert_not_awaited()
        mocks["publish_tarot_reading_generate"].assert_not_awaited()
        mocks["release_reading_lock"].assert_awaited_once()
        state.clear.assert_awaited_once()

    async def test_skip_allowed_creates_draft_without_question(self):
        message = _message(BTN_TAROT_SKIP)
        state = _state({"tarot_spread_type": "three_cards"})
        mocks = _mocks()
        await _run(spread_question, message, state, AsyncMock(), mocks)
        assert mocks["create_reading_draft"].await_args.args[3] is None  # question
        message.answer_invoice.assert_awaited_once()

    async def test_double_tap_lock(self):
        message, state = _message("Стоит ли менять работу этим летом?"), _state(self._DATA)
        mocks = _mocks(try_acquire_reading_lock=AsyncMock(return_value=False))
        await _run(spread_question, message, state, AsyncMock(), mocks)
        mocks["create_reading_draft"].assert_not_awaited()
        message.answer.assert_not_called()
        assert "секунду" in _screen_text(mocks)


def _reading(status: ReadingStatus = ReadingStatus.PENDING_PAYMENT, **overrides) -> MagicMock:
    reading = MagicMock()
    reading.id = uuid4()
    reading.user_id = uuid4()
    reading.spread_type = str(SpreadType.WISH)
    reading.status = status
    reading.cards = [
        {"position": 1, "position_key": "heart", "card_id": "cups_06", "reversed": False},
        {"position": 2, "position_key": "path", "card_id": "swords_03", "reversed": False},
        {"position": 3, "position_key": "outcome", "card_id": "major_06", "reversed": False},
    ]
    for key, value in overrides.items():
        setattr(reading, key, value)
    return reading


class TestPreCheckout:
    def _query(self, payload: str) -> MagicMock:
        query = MagicMock()
        query.invoice_payload = payload
        query.answer = AsyncMock()
        return query

    async def test_ok_for_pending_payment_draft(self):
        reading = _reading()
        query = self._query(f"tarot:{reading.id}")
        with patch(f"{_MODULE}.get_reading", AsyncMock(return_value=reading)):
            await pre_checkout(query, AsyncMock())
        query.answer.assert_awaited_once_with(ok=True)

    async def test_rejects_already_paid_draft(self):
        reading = _reading(status=ReadingStatus.PENDING)
        query = self._query(f"tarot:{reading.id}")
        with patch(f"{_MODULE}.get_reading", AsyncMock(return_value=reading)):
            await pre_checkout(query, AsyncMock())
        assert query.answer.call_args.kwargs["ok"] is False

    async def test_rejects_bad_payload(self):
        query = self._query("что-то чужое")
        await pre_checkout(query, AsyncMock())
        assert query.answer.call_args.kwargs["ok"] is False


class TestSpreadPaid:
    def _paid_message(self, payload: str) -> MagicMock:
        message = _message("")
        message.text = None
        message.successful_payment = MagicMock(
            invoice_payload=payload,
            telegram_payment_charge_id="charge-1",
            total_amount=50,
            currency="XTR",
        )
        message.bot = MagicMock()
        message.bot.refund_star_payment = AsyncMock()
        return message

    async def test_payment_reveals_cards_and_publishes(self):
        user = _user()
        reading = _reading(user_id=user.id)
        message = self._paid_message(f"tarot:{reading.id}")
        session = AsyncMock()
        mocks = _mocks(
            **{"users_crud.get_user_by_telegram_id": AsyncMock(return_value=user)},
            get_reading=AsyncMock(return_value=reading),
            register_tarot_payment=AsyncMock(return_value=MagicMock()),
            mark_reading_paid=AsyncMock(),
        )
        with ExitStack() as stack:
            for name, mock in mocks.items():
                stack.enter_context(patch(f"{_MODULE}.{name}", mock))
            await spread_paid(message, session)
        mocks["register_tarot_payment"].assert_awaited_once()
        mocks["mark_reading_paid"].assert_awaited_once()
        session.commit.assert_awaited_once()
        mocks["send_cards_album"].assert_awaited_once()
        mocks["publish_tarot_reading_generate"].assert_awaited_once_with(reading.id)

    async def test_duplicate_charge_is_ignored(self):
        user = _user()
        reading = _reading(user_id=user.id)
        message = self._paid_message(f"tarot:{reading.id}")
        session = AsyncMock()
        mocks = _mocks(
            **{"users_crud.get_user_by_telegram_id": AsyncMock(return_value=user)},
            get_reading=AsyncMock(return_value=reading),
            register_tarot_payment=AsyncMock(return_value=None),  # дубль
            mark_reading_paid=AsyncMock(),
        )
        with ExitStack() as stack:
            for name, mock in mocks.items():
                stack.enter_context(patch(f"{_MODULE}.{name}", mock))
            await spread_paid(message, session)
        mocks["send_cards_album"].assert_not_awaited()
        mocks["publish_tarot_reading_generate"].assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_orphan_payment_is_refunded(self):
        message = self._paid_message(f"tarot:{uuid4()}")
        mocks = _mocks(
            **{"users_crud.get_user_by_telegram_id": AsyncMock(return_value=_user())},
            get_reading=AsyncMock(return_value=None),
        )
        with ExitStack() as stack:
            for name, mock in mocks.items():
                stack.enter_context(patch(f"{_MODULE}.{name}", mock))
            await spread_paid(message, AsyncMock())
        message.bot.refund_star_payment.assert_awaited_once()
        mocks["send_cards_album"].assert_not_awaited()


class TestSpreadButtonsMapping:
    def test_entry_buttons_map_to_spreads(self):
        from astra.telegram.button_texts import (
            BTN_TAROT_DECISION_LEGACY,
            BTN_TAROT_RELATIONS,
            BTN_TAROT_THREE,
        )
        from astra.telegram.handlers.tarot_spreads import SPREAD_BUTTONS

        assert SPREAD_BUTTONS[BTN_TAROT_THREE] is SpreadType.THREE_CARDS
        assert SPREAD_BUTTONS[BTN_TAROT_RELATIONS] is SpreadType.RELATIONSHIP
        assert SPREAD_BUTTONS[BTN_TAROT_WISH] is SpreadType.WISH
        # старая кнопка «На решение» у закэшированных клиентов теперь ведёт в «Желание»
        assert SPREAD_BUTTONS[BTN_TAROT_DECISION_LEGACY] is SpreadType.WISH


class TestInlineScreen:
    """Раздел на inline-экране: выбор расклада, «Пропустить», выход."""

    def _callback(self, data: str) -> MagicMock:
        callback = MagicMock()
        callback.data = data
        callback.answer = AsyncMock()
        callback.from_user = MagicMock(id=100500)
        callback.message = MagicMock(spec=Message)
        callback.message.answer = AsyncMock()
        callback.message.answer_invoice = AsyncMock()
        return callback

    async def _run_cb(self, handler, mocks: dict, *args) -> None:
        with ExitStack() as stack:
            for name, mock in mocks.items():
                stack.enter_context(patch(f"{_MODULE}.{name}", mock))
            await handler(*args)

    async def test_hub_lists_three_spreads(self):
        callback = self._callback(CB_TAROT_SECTION)
        mocks = _mocks()
        state = _state()

        await self._run_cb(cb_open_spreads, mocks, callback, state)

        state.clear.assert_awaited_once()
        callback.message.answer.assert_not_called()
        markup = mocks["show_screen"].call_args.kwargs["reply_markup"]
        data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        assert data == [
            f"{CB_TAROT_SPREAD_PREFIX}three_cards",
            f"{CB_TAROT_SPREAD_PREFIX}relationship",
            f"{CB_TAROT_SPREAD_PREFIX}wish",
            CB_TAROT_CLOSE,
        ]

    async def test_picking_spread_asks_question_in_same_screen(self):
        callback = self._callback(f"{CB_TAROT_SPREAD_PREFIX}wish")
        state, mocks = _state(), _mocks()

        await self._run_cb(cb_pick_spread, mocks, callback, state, AsyncMock())

        state.set_state.assert_awaited_once_with(TarotStates.waiting_question)
        state.update_data.assert_awaited_once_with(tarot_spread_type="wish")
        callback.message.answer.assert_not_called()
        assert "желание" in _screen_text(mocks).lower()

    async def test_unknown_user_is_refused_with_alert(self):
        callback = self._callback(f"{CB_TAROT_SPREAD_PREFIX}wish")
        mocks = _mocks(**{"users_crud.get_user_by_telegram_id": AsyncMock(return_value=None)})

        await self._run_cb(cb_pick_spread, mocks, callback, _state(), AsyncMock())

        mocks["show_screen"].assert_not_awaited()
        assert callback.answer.call_args.kwargs["show_alert"] is True

    async def test_skip_button_creates_draft_without_question(self):
        callback = self._callback(CB_TAROT_QUESTION_SKIP)
        state = _state({"tarot_spread_type": "three_cards"})
        mocks = _mocks()

        await self._run_cb(cb_skip_question, mocks, callback, state, AsyncMock())

        assert mocks["create_reading_draft"].await_args.args[3] is None  # question
        callback.message.answer_invoice.assert_awaited_once()

    async def test_close_hides_screen(self):
        callback = self._callback(CB_TAROT_CLOSE)
        state, mocks = _state(), _mocks()

        await self._run_cb(cb_close_spreads, mocks, callback, state)

        state.clear.assert_awaited_once()
        mocks["close_screen"].assert_awaited_once()
        callback.message.answer.assert_not_called()
