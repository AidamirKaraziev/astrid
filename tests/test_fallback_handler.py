"""Никакое сообщение не остаётся без ответа.

Молчание бота — самый дорогой отказ: человек не понимает, сломалось ли что-то
и что делать дальше, и уходит, не написав ни слова в поддержку. Отдельно
проверяется состояние, пережившее деплой: шага с таким именем больше нет, и
человек застревает в нём навсегда, пока сам не догадается набрать /start.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from astra.telegram.handlers import fallback
from astra.telegram.handlers.fallback import (
    LOST_IN_MENU_TEXT,
    LOST_IN_ONBOARDING_TEXT,
    STALE_BUTTON_TEXT,
    UNKNOWN_COMMAND_TEXT,
    unhandled_callback,
    unhandled_message,
)


async def _fsm() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=2, user_id=3))


def _message(text: str = "15.03.1990") -> MagicMock:
    message = MagicMock()
    message.text = text
    message.content_type = "text"
    message.from_user = SimpleNamespace(id=777)
    message.answer = AsyncMock()
    return message


def _user(*, completed: bool):
    return SimpleNamespace(id=uuid4(), telegram_id=777, onboarding_completed=completed)


def _patch_user(user):
    return patch.object(
        fallback.users_crud,
        "get_user_by_telegram_id",
        AsyncMock(return_value=user),
    )


@pytest.mark.asyncio
async def test_stale_state_from_deploy_does_not_trap_the_person() -> None:
    """Состояние пережило выкатку, шага уже нет — человека надо расклинить."""
    state = await _fsm()
    await state.set_state("OnboardingStates:birth_date")  # шага больше не существует
    message = _message()

    with _patch_user(_user(completed=True)):
        await unhandled_message(message, state, MagicMock())

    assert await state.get_state() is None, "человек остался в несуществующем шаге"
    message.answer.assert_awaited_once()
    assert message.answer.await_args.args[0] == LOST_IN_MENU_TEXT
    assert message.answer.await_args.kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_unregistered_person_is_sent_to_start() -> None:
    message = _message("привет")

    with _patch_user(None):
        await unhandled_message(message, await _fsm(), MagicMock())

    assert message.answer.await_args.args[0] == LOST_IN_ONBOARDING_TEXT


@pytest.mark.asyncio
async def test_half_registered_person_is_sent_to_start() -> None:
    message = _message("привет")

    with _patch_user(_user(completed=False)):
        await unhandled_message(message, await _fsm(), MagicMock())

    assert message.answer.await_args.args[0] == LOST_IN_ONBOARDING_TEXT


@pytest.mark.asyncio
async def test_unknown_command_says_so_without_touching_the_database() -> None:
    message = _message("/gadanie")
    lookup = AsyncMock()

    with patch.object(fallback.users_crud, "get_user_by_telegram_id", lookup):
        await unhandled_message(message, await _fsm(), MagicMock())

    assert message.answer.await_args.args[0] == UNKNOWN_COMMAND_TEXT
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_without_state_is_answered_too() -> None:
    """Человек просто написал боту — тоже не молчим."""
    state = await _fsm()
    message = _message("а когда будет прогноз?")

    with _patch_user(_user(completed=True)):
        await unhandled_message(message, state, MagicMock())

    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_stale_button_gets_an_answer_instead_of_a_spinner() -> None:
    """Без ответа на callback Telegram крутит часики, пока человек не уйдёт."""
    callback = MagicMock()
    callback.data = "wheel:use:0f3c"
    callback.answer = AsyncMock()

    await unhandled_callback(callback)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.args[0] == STALE_BUTTON_TEXT
