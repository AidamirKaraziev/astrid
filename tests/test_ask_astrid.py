"""Раздел «Спроси Астрид»: верхний уровень — темы вопросов."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from astra.telegram import ask_text as A
from astra.telegram.button_texts import (
    BTN_ASK_ASTRID,
    BTN_HELP,
    CB_ASK_CLOSE,
    CB_ASK_HOME,
    CB_ASK_OWN,
    CB_ASK_TOPIC_PREFIX,
)
from astra.telegram.handlers import ask_astrid
from astra.telegram.keyboard_policy import MAIN_MENU_BUTTONS
from astra.telegram.keyboards import ask_astrid_keyboard, main_menu_keyboard


async def _fsm() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=2, user_id=3))


def _callback(data: str | None = None) -> MagicMock:
    callback = MagicMock(spec=CallbackQuery)
    callback.answer = AsyncMock()
    callback.data = data
    callback.message = MagicMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.message.answer = AsyncMock()
    callback.message.delete = AsyncMock()
    return callback


# ─────────────────────────── клавиатуры ───────────────────────────


def test_main_menu_has_ask_astrid_under_wheel() -> None:
    rows = [[btn.text for btn in row] for row in main_menu_keyboard().keyboard]
    assert rows[1] == [BTN_ASK_ASTRID]
    assert BTN_ASK_ASTRID in MAIN_MENU_BUTTONS


def test_ask_astrid_name_does_not_collide_with_support() -> None:
    # «Помощь» — про бота, «Спроси Астрид» — про карту: разные разделы.
    assert BTN_ASK_ASTRID != BTN_HELP


def test_hub_keyboard_lists_all_topics_then_own_question_and_close() -> None:
    rows = ask_astrid_keyboard().inline_keyboard
    data = [btn.callback_data for row in rows for btn in row]
    labels = [btn.text for row in rows for btn in row]

    assert data[: len(A.ASK_TOPICS)] == [f"{CB_ASK_TOPIC_PREFIX}{key}" for key, _ in A.ASK_TOPICS]
    assert labels[: len(A.ASK_TOPICS)] == [label for _, label in A.ASK_TOPICS]
    assert data[-2:] == [CB_ASK_OWN, CB_ASK_CLOSE]
    assert len(A.ASK_TOPICS) == 8


def test_every_topic_is_one_full_width_row() -> None:
    rows = ask_astrid_keyboard().inline_keyboard
    assert all(len(row) == 1 for row in rows)


# ─────────────────────────── вход в раздел ───────────────────────────


@pytest.mark.asyncio
async def test_menu_button_opens_hub_and_clears_state() -> None:
    state = await _fsm()
    await state.set_data({"stale": True})
    message = MagicMock(spec=Message)
    message.answer = AsyncMock()

    await ask_astrid.ask_astrid_button(message, state)

    assert await state.get_state() is None
    assert message.answer.await_args.args[0] == A.ASK_HUB_TEXT


# ─────────────────────────── темы ───────────────────────────


@pytest.mark.asyncio
async def test_topic_says_questions_are_coming() -> None:
    callback = _callback(f"{CB_ASK_TOPIC_PREFIX}{A.ASK_TOPIC_LOVE}")

    await ask_astrid.cb_ask_topic(callback)

    text = callback.message.edit_text.await_args.args[0]
    assert A.ASK_TOPIC_LABELS[A.ASK_TOPIC_LOVE] in text
    assert "скоро" in text.lower()


@pytest.mark.asyncio
async def test_unknown_topic_is_ignored() -> None:
    callback = _callback(f"{CB_ASK_TOPIC_PREFIX}unknown")

    await ask_astrid.cb_ask_topic(callback)

    callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_topic_screen_returns_to_topics() -> None:
    callback = _callback(f"{CB_ASK_TOPIC_PREFIX}{A.ASK_TOPIC_NOW}")
    await ask_astrid.cb_ask_topic(callback)
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].callback_data == CB_ASK_HOME

    back = _callback(CB_ASK_HOME)
    await ask_astrid.cb_ask_home(back)
    assert back.message.edit_text.await_args.args[0] == A.ASK_HUB_TEXT


@pytest.mark.asyncio
async def test_topic_falls_back_to_new_message_when_edit_fails() -> None:
    callback = _callback(f"{CB_ASK_TOPIC_PREFIX}{A.ASK_TOPIC_MONEY}")
    callback.message.edit_text = AsyncMock(side_effect=Exception("message has photo"))

    await ask_astrid.cb_ask_topic(callback)

    assert A.ASK_TOPIC_LABELS[A.ASK_TOPIC_MONEY] in callback.message.answer.await_args.args[0]


# ─────────────────────────── свой вопрос и закрытие ───────────────────────────


@pytest.mark.asyncio
async def test_own_question_says_it_is_coming() -> None:
    callback = _callback(CB_ASK_OWN)

    await ask_astrid.cb_ask_own(callback)

    assert callback.message.edit_text.await_args.args[0] == A.ASK_OWN_SOON_TEXT


@pytest.mark.asyncio
async def test_close_deletes_message() -> None:
    callback = _callback(CB_ASK_CLOSE)

    await ask_astrid.cb_ask_close(callback)

    callback.message.delete.assert_awaited_once()
