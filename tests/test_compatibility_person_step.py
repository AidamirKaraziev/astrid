"""Единый экран выбора человека в совместимости: сохранённые + «Новый человек»."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from astra.compatibility.enums import PairMode
from astra.telegram.button_texts import (
    CB_COMPAT_CONTEXT_PREFIX,
    CB_COMPAT_NEW_PERSON,
    CB_COMPAT_PEOPLE_ALL,
    CB_COMPAT_SELF_FIRST,
    CB_PERSON_PICK_PREFIX,
)
from astra.telegram.handlers.compatibility import (
    _compat_person_keyboard,
    _send_person_step,
    cb_choose_context,
    cb_compat_new_person,
    cb_compat_self_first,
)
from astra.telegram.states import CompatibilityStates


async def _fsm() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=2, user_id=3))


def _profile() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        label="Анжела",
        gender="женщина",
        birth_date=date(2001, 12, 2),
    )


def _message() -> AsyncMock:
    message = AsyncMock()
    message.answer = AsyncMock()
    return message


def test_compat_person_keyboard_collapses_and_has_actions() -> None:
    profiles = [_profile() for _ in range(9)]
    kb = _compat_person_keyboard(profiles)
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert CB_COMPAT_NEW_PERSON in callbacks
    assert CB_COMPAT_PEOPLE_ALL in callbacks
    assert sum(1 for c in callbacks if c.startswith(CB_PERSON_PICK_PREFIX)) == 6

    full = _compat_person_keyboard(profiles, show_all=True)
    full_cb = [b.callback_data for row in full.inline_keyboard for b in row]
    assert sum(1 for c in full_cb if c.startswith(CB_PERSON_PICK_PREFIX)) == 9
    assert CB_COMPAT_PEOPLE_ALL not in full_cb


@pytest.mark.asyncio
async def test_send_person_step_no_profiles_asks_name_directly() -> None:
    state = await _fsm()
    message = _message()
    session = AsyncMock()
    user = MagicMock(id=uuid4())

    with (
        patch(
            "astra.telegram.handlers.compatibility.users_crud.get_user_by_telegram_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "astra.telegram.handlers.compatibility.compatibility_crud.list_natal_profiles",
            new=AsyncMock(return_value=[]),
        ),
    ):
        await _send_person_step(
            message, state, session,
            actor_telegram_id=42,
            heading="👥 Кто партнёр?",
            name_prompt="Как зовут партнёра?",
        )

    assert await state.get_state() == CompatibilityStates.collect_name.state
    text = message.answer.await_args.args[0]
    assert "Как зовут" in text
    # без клавиатуры выбора
    assert "reply_markup" in message.answer.await_args.kwargs


@pytest.mark.asyncio
async def test_send_person_step_with_profiles_shows_selection() -> None:
    state = await _fsm()
    message = _message()
    session = AsyncMock()
    user = MagicMock(id=uuid4())

    with (
        patch(
            "astra.telegram.handlers.compatibility.users_crud.get_user_by_telegram_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "astra.telegram.handlers.compatibility.compatibility_crud.list_natal_profiles",
            new=AsyncMock(return_value=[_profile(), _profile()]),
        ),
    ):
        await _send_person_step(
            message, state, session,
            actor_telegram_id=42,
            heading="👥 Кто партнёр?",
            name_prompt="Как зовут партнёра?",
        )

    kb = message.answer.await_args.kwargs["reply_markup"]
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert CB_COMPAT_NEW_PERSON in callbacks


def _cb(data: str) -> AsyncMock:
    callback = AsyncMock()
    callback.data = data
    callback.answer = AsyncMock()
    callback.from_user = MagicMock(id=42)
    callback.message = _message()
    return callback


@pytest.mark.asyncio
async def test_context_goes_straight_to_first_person_with_self() -> None:
    # выбор контекста ведёт сразу к первому участнику, без шага режима
    state = await _fsm()
    callback = _cb(f"{CB_COMPAT_CONTEXT_PREFIX}love")
    session = AsyncMock()
    user = MagicMock(id=uuid4())

    with (
        patch(
            "astra.telegram.handlers.compatibility.users_crud.get_user_by_telegram_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "astra.telegram.handlers.compatibility.compatibility_crud.list_natal_profiles",
            new=AsyncMock(return_value=[]),
        ),
    ):
        await cb_choose_context(callback, state, session)

    assert await state.get_state() == CompatibilityStates.collect_name.state
    data = await state.get_data()
    assert data["relationship_context"] == "love"
    assert data["pair_mode"] == PairMode.TWO_PEOPLE.value  # по умолчанию
    kb = callback.message.answer.await_args.kwargs["reply_markup"]
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert CB_COMPAT_SELF_FIRST in callbacks  # «Я» доступен даже без сохранённых


@pytest.mark.asyncio
async def test_self_first_switches_to_me_partner_and_asks_partner() -> None:
    state = await _fsm()
    await state.set_state(CompatibilityStates.collect_name)
    await state.update_data(pair_mode=PairMode.TWO_PEOPLE.value, collecting="person_a")
    callback = _cb(CB_COMPAT_SELF_FIRST)
    session = AsyncMock()
    user = MagicMock(id=uuid4())

    with (
        patch(
            "astra.telegram.handlers.compatibility.users_crud.get_user_by_telegram_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "astra.telegram.handlers.compatibility.compatibility_crud.list_natal_profiles",
            new=AsyncMock(return_value=[]),
        ),
    ):
        await cb_compat_self_first(callback, state, session)

    data = await state.get_data()
    assert data["pair_mode"] == PairMode.ME_PARTNER.value
    assert data["collecting"] == "person_b"
    text = callback.message.answer.await_args.args[0]
    assert "партнёр" in text.lower()


@pytest.mark.asyncio
async def test_new_person_reasks_stored_name_prompt() -> None:
    state = await _fsm()
    await state.set_state(CompatibilityStates.collect_name)
    await state.update_data(person_step_name_prompt="Как зовут <b>партнёра</b>?")
    callback = AsyncMock()
    callback.message = _message()
    callback.answer = AsyncMock()

    await cb_compat_new_person(callback, state)

    text = callback.message.answer.await_args.args[0]
    assert "Как зовут" in text
    assert await state.get_state() == CompatibilityStates.collect_name.state
