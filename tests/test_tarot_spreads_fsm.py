"""Тесты FSM платных раскладов: вход, вопрос, лимит, даблтап, назад."""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from astra.tarot.spreads import SpreadType
from astra.telegram.button_texts import (
    BTN_BACK_MENU,
    BTN_TAROT_DECISION,
    BTN_TAROT_SKIP,
    BTN_TAROT_UNLOCK,
    CB_TAROT_UNLOCK,
)
from astra.telegram.handlers.tarot_spreads import (
    cb_tarot_unlock,
    spread_button,
    spread_question,
)
from astra.telegram.states import TarotStates

_MODULE = "astra.telegram.handlers.tarot_spreads"


def _message(text: str) -> MagicMock:
    message = MagicMock()
    message.text = text
    message.from_user = MagicMock(id=100500)
    message.answer = AsyncMock()
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
    return user


def _mocks(**overrides) -> dict:
    defaults = {
        "users_crud.get_user_by_telegram_id": AsyncMock(return_value=_user()),
        "check_daily_limit": AsyncMock(return_value=True),
        "try_acquire_reading_lock": AsyncMock(return_value=True),
        "release_reading_lock": AsyncMock(),
        "create_reading": AsyncMock(return_value=(MagicMock(id=uuid4()), [MagicMock()])),
        "send_card_photo": AsyncMock(),
        "send_cards_album": AsyncMock(),
        "publish_tarot_reading_generate": AsyncMock(),
    }
    defaults.update(overrides)
    return defaults


async def _run(handler, message, state, session, mocks: dict) -> None:
    with ExitStack() as stack:
        for name, mock in mocks.items():
            stack.enter_context(patch(f"{_MODULE}.{name}", mock))
        await handler(message, state, session)


class TestSpreadButton:
    async def test_sets_state_and_asks_question(self):
        message, state = _message(BTN_TAROT_DECISION), _state()
        await _run(spread_button, message, state, AsyncMock(), _mocks())
        state.set_state.assert_awaited_once_with(TarotStates.waiting_question)
        state.update_data.assert_awaited_once_with(tarot_spread_type="yes_no")
        assert "да" in message.answer.call_args.args[0].lower()

    async def test_limit_hit_shows_unlock_button(self):
        message, state = _message(BTN_TAROT_DECISION), _state()
        await _run(
            spread_button, message, state, AsyncMock(),
            _mocks(check_daily_limit=AsyncMock(return_value=False)),
        )
        state.set_state.assert_not_awaited()
        assert "разложены" in message.answer.call_args.args[0]
        markup = message.answer.call_args.kwargs["reply_markup"]
        assert markup.inline_keyboard[0][0].text == BTN_TAROT_UNLOCK
        assert markup.inline_keyboard[0][0].callback_data == CB_TAROT_UNLOCK

    async def test_requires_onboarded_user(self):
        message, state = _message(BTN_TAROT_DECISION), _state()
        await _run(
            spread_button, message, state, AsyncMock(),
            _mocks(**{"users_crud.get_user_by_telegram_id": AsyncMock(return_value=None)}),
        )
        state.set_state.assert_not_awaited()
        assert "/start" in message.answer.call_args.args[0]


class TestSpreadQuestion:
    _DATA = {"tarot_spread_type": "yes_no"}

    async def test_back_returns_to_main_menu(self):
        message, state = _message(BTN_BACK_MENU), _state(self._DATA)
        await _run(spread_question, message, state, AsyncMock(), _mocks())
        state.clear.assert_awaited_once()
        assert "меню" in message.answer.call_args.args[0].lower()

    async def test_too_short_question_reprompts(self):
        message, state = _message("Да"), _state(self._DATA)
        mocks = _mocks()
        await _run(spread_question, message, state, AsyncMock(), mocks)
        mocks["create_reading"].assert_not_awaited()
        assert "символов" in message.answer.call_args.args[0]

    async def test_skip_rejected_when_question_required(self):
        message, state = _message(BTN_TAROT_SKIP), _state(self._DATA)
        mocks = _mocks()
        await _run(spread_question, message, state, AsyncMock(), mocks)
        mocks["create_reading"].assert_not_awaited()

    async def test_unknown_spread_type_resets(self):
        message, state = _message("Нормальный вопрос?"), _state({})
        mocks = _mocks()
        await _run(spread_question, message, state, AsyncMock(), mocks)
        state.clear.assert_awaited_once()
        mocks["create_reading"].assert_not_awaited()

    async def test_valid_question_creates_and_publishes(self):
        message, state = _message("Стоит ли менять работу этим летом?"), _state(self._DATA)
        session, mocks = AsyncMock(), _mocks()
        await _run(spread_question, message, state, session, mocks)
        mocks["create_reading"].assert_awaited_once()
        assert mocks["create_reading"].await_args.args[2] is SpreadType.YES_NO
        session.commit.assert_awaited_once()
        mocks["send_card_photo"].assert_awaited_once()
        mocks["publish_tarot_reading_generate"].assert_awaited_once()
        mocks["release_reading_lock"].assert_awaited_once()
        state.clear.assert_awaited_once()

    async def test_double_tap_lock(self):
        message, state = _message("Стоит ли менять работу этим летом?"), _state(self._DATA)
        mocks = _mocks(try_acquire_reading_lock=AsyncMock(return_value=False))
        await _run(spread_question, message, state, AsyncMock(), mocks)
        mocks["create_reading"].assert_not_awaited()
        assert "секунду" in message.answer.call_args.args[0]

    async def test_limit_recheck_after_lock(self):
        message, state = _message("Стоит ли менять работу этим летом?"), _state(self._DATA)
        mocks = _mocks(check_daily_limit=AsyncMock(return_value=False))
        await _run(spread_question, message, state, AsyncMock(), mocks)
        mocks["create_reading"].assert_not_awaited()
        mocks["release_reading_lock"].assert_awaited_once()


class TestMultiCardSpreads:
    async def test_three_cards_skip_creates_without_question(self):
        message = _message(BTN_TAROT_SKIP)
        state = _state({"tarot_spread_type": "three_cards"})
        mocks = _mocks(
            create_reading=AsyncMock(
                return_value=(MagicMock(id=uuid4()), [MagicMock()] * 3),
            ),
        )
        await _run(spread_question, message, state, AsyncMock(), mocks)
        assert mocks["create_reading"].await_args.args[3] is None  # question
        mocks["send_cards_album"].assert_awaited_once()
        mocks["send_card_photo"].assert_not_awaited()

    async def test_relationship_sends_five_card_album(self):
        message = _message("Что происходит между мной и Сашей?")
        state = _state({"tarot_spread_type": "relationship"})
        mocks = _mocks(
            create_reading=AsyncMock(
                return_value=(MagicMock(id=uuid4()), [MagicMock()] * 5),
            ),
        )
        await _run(spread_question, message, state, AsyncMock(), mocks)
        assert mocks["create_reading"].await_args.args[2] is SpreadType.RELATIONSHIP
        cards_sent = mocks["send_cards_album"].await_args.args[1]
        assert len(cards_sent) == 5
        mocks["publish_tarot_reading_generate"].assert_awaited_once()

    async def test_entry_buttons_map_to_spreads(self):
        from astra.telegram.button_texts import BTN_TAROT_RELATIONS, BTN_TAROT_THREE
        from astra.telegram.handlers.tarot_spreads import SPREAD_BUTTONS

        assert SPREAD_BUTTONS[BTN_TAROT_THREE] is SpreadType.THREE_CARDS
        assert SPREAD_BUTTONS[BTN_TAROT_RELATIONS] is SpreadType.RELATIONSHIP


class TestUnlock:
    def _callback(self) -> MagicMock:
        callback = MagicMock()
        callback.data = CB_TAROT_UNLOCK
        callback.from_user = MagicMock(id=100500)
        callback.answer = AsyncMock()
        callback.message = MagicMock()
        callback.message.answer = AsyncMock()
        callback.message.edit_reply_markup = AsyncMock()
        return callback

    async def test_grants_bonus_and_opens_menu(self):
        callback = self._callback()
        user = _user()
        with (
            patch(
                "astra.telegram.handlers.tarot_spreads.users_crud.get_user_by_telegram_id",
                AsyncMock(return_value=user),
            ),
            patch(
                "astra.telegram.handlers.tarot_spreads.grant_bonus_reading",
                AsyncMock(return_value=1),
            ) as grant,
            patch("astra.telegram.handlers.tarot_spreads.tarot_keyboard", MagicMock()),
        ):
            await cb_tarot_unlock(callback, AsyncMock())
        grant.assert_awaited_once()
        callback.answer.assert_awaited_once()
        callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
        callback.message.answer.assert_awaited_once()

    async def test_requires_user(self):
        callback = self._callback()
        with (
            patch(
                "astra.telegram.handlers.tarot_spreads.users_crud.get_user_by_telegram_id",
                AsyncMock(return_value=None),
            ),
            patch(
                "astra.telegram.handlers.tarot_spreads.grant_bonus_reading",
                AsyncMock(),
            ) as grant,
        ):
            await cb_tarot_unlock(callback, AsyncMock())
        grant.assert_not_awaited()
