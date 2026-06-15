from unittest.mock import MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, User

from astra.telegram.auto_keyboard_middleware import AutoKeyboardMiddleware
from astra.telegram.button_texts import BTN_COMPATIBILITY, BTN_PREDICTION_TODAY
from astra.telegram.keyboards import main_menu_keyboard


def _message(text: str) -> Message:
    return Message(
        message_id=1,
        date=0,
        chat=Chat(id=1, type="private"),
        from_user=User(id=1, is_bot=False, first_name="Test"),
        text=text,
    )


def _fsm() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def _patch_and_answer(message: Message, data: dict) -> dict:
    captured: dict = {}

    async def original_answer(text: str = "", **kwargs):
        captured["text"] = text
        captured.update(kwargs)
        return message

    object.__setattr__(message, "answer", original_answer)
    middleware = AutoKeyboardMiddleware()
    await middleware._patch_message_answer(message, data)
    await message.answer("готово")
    return captured


@pytest.mark.asyncio
async def test_middleware_attaches_main_menu_when_reply_markup_missing() -> None:
    message = _message(BTN_PREDICTION_TODAY)
    fsm = _fsm()
    await fsm.clear()

    captured = await _patch_and_answer(message, {"state": fsm, "handler": MagicMock(flags={})})

    assert captured["text"] == "готово"
    assert captured["reply_markup"] == main_menu_keyboard()


@pytest.mark.asyncio
async def test_middleware_does_not_override_explicit_reply_markup() -> None:
    message = _message(BTN_PREDICTION_TODAY)
    fsm = _fsm()
    custom_markup = main_menu_keyboard()

    captured: dict = {}

    async def original_answer(text: str = "", **kwargs):
        captured["text"] = text
        captured.update(kwargs)
        return message

    object.__setattr__(message, "answer", original_answer)
    middleware = AutoKeyboardMiddleware()
    await middleware._patch_message_answer(
        message,
        {"state": fsm, "handler": MagicMock(flags={})},
    )
    await message.answer("готово", reply_markup=custom_markup)

    assert captured["reply_markup"] is custom_markup


@pytest.mark.asyncio
async def test_middleware_keeps_main_zone_for_paid_stub() -> None:
    message = _message(BTN_COMPATIBILITY)
    fsm = _fsm()

    captured = await _patch_and_answer(message, {"state": fsm, "handler": MagicMock(flags={})})

    assert captured["reply_markup"] == main_menu_keyboard()
