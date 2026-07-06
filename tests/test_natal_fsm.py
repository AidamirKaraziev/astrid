"""FSM разбора натала: время спрашивается только при отсутствии, путь «не знаю»."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from astra.telegram.button_texts import BTN_NATAL
from astra.telegram.handlers.natal import collect_birth_time, start_natal
from astra.telegram.states import NatalStates


async def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=2, user_id=3)
    return FSMContext(storage=storage, key=key)


def _user(*, birth_time: datetime | None) -> MagicMock:
    user = MagicMock()
    user.onboarding_completed = True
    profile = MagicMock()
    profile.display_name = "Айдамир"
    profile.birth_date = date(1990, 6, 15)
    profile.birth_time = birth_time
    profile.birth_place = "Москва"
    user.profile = profile
    return user


def _message() -> AsyncMock:
    message = AsyncMock()
    message.text = BTN_NATAL
    message.answer = AsyncMock()
    message.from_user = MagicMock()
    message.from_user.id = 42
    return message


@pytest.mark.anyio
async def test_start_natal_asks_time_when_missing() -> None:
    state = await _fsm_context()
    message = _message()
    session = AsyncMock()

    with patch(
        "astra.telegram.handlers.natal.users_crud.get_user_by_telegram_id",
        new=AsyncMock(return_value=_user(birth_time=None)),
    ):
        await start_natal(message, state, session)

    assert await state.get_state() == NatalStates.collect_birth_time.state
    text = message.answer.await_args.args[0]
    assert "время рождения" in text.lower()


@pytest.mark.anyio
async def test_start_natal_skips_time_when_present() -> None:
    state = await _fsm_context()
    message = _message()
    session = AsyncMock()

    with patch(
        "astra.telegram.handlers.natal.users_crud.get_user_by_telegram_id",
        new=AsyncMock(return_value=_user(birth_time=datetime(1990, 6, 15, 14, 30))),
    ):
        await start_natal(message, state, session)

    assert await state.get_state() == NatalStates.confirm.state
    text = message.answer.await_args.args[0]
    assert "14:30" in text
    assert "Без времени рождения" not in text


@pytest.mark.anyio
async def test_confirm_without_time_shows_degradation_warning() -> None:
    state = await _fsm_context()
    message = _message()
    session = AsyncMock()
    user = _user(birth_time=None)

    with patch(
        "astra.telegram.handlers.natal.users_crud.get_user_by_telegram_id",
        new=AsyncMock(return_value=user),
    ):
        await start_natal(message, state, session)
        # пользователь вводит время текстом
        message.text = "abc"
        await collect_birth_time(message, state, session)

    # невалидное время — остаёмся в состоянии сбора
    assert await state.get_state() == NatalStates.collect_birth_time.state


@pytest.mark.anyio
async def test_collect_birth_time_saves_and_confirms() -> None:
    state = await _fsm_context()
    await state.set_state(NatalStates.collect_birth_time)
    message = _message()
    message.text = "14:30"
    session = AsyncMock()
    user = _user(birth_time=None)

    with (
        patch(
            "astra.telegram.handlers.natal.users_crud.get_user_by_telegram_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "astra.telegram.handlers.natal.users_crud.update_profile",
            new=AsyncMock(),
        ) as update_mock,
    ):
        await collect_birth_time(message, state, session)

    update_mock.assert_awaited_once()
    saved = update_mock.await_args.kwargs["birth_time"]
    assert saved == datetime(1990, 6, 15, 14, 30)
    assert await state.get_state() == NatalStates.confirm.state
