from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from astra.telegram.button_texts import BTN_GENDER_FEMALE, BTN_GENDER_MALE
from astra.telegram.handlers.onboarding import onboarding_gender
from astra.telegram.keyboards import gender_keyboard
from astra.telegram.states import OnboardingStates
from astra.users.gender import GENDER_FEMALE, GENDER_MALE


async def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=2, user_id=3)
    return FSMContext(storage=storage, key=key)


@pytest.mark.anyio
async def test_onboarding_gender_saves_and_advances() -> None:
    state = await _fsm_context()
    await state.set_state(OnboardingStates.gender)

    message = AsyncMock()
    message.text = BTN_GENDER_MALE
    message.answer = AsyncMock()

    await onboarding_gender(message, state)

    data = await state.get_data()
    assert data["gender"] == GENDER_MALE
    assert await state.get_state() == OnboardingStates.birth_date.state
    message.answer.assert_awaited_once()
    assert message.answer.await_args.kwargs.get("reply_markup") is not None


@pytest.mark.anyio
async def test_onboarding_gender_invalid_input_reprompts() -> None:
    state = await _fsm_context()
    await state.set_state(OnboardingStates.gender)

    message = AsyncMock()
    message.text = "не знаю"
    message.answer = AsyncMock()

    await onboarding_gender(message, state)

    assert await state.get_state() == OnboardingStates.gender.state
    message.answer.assert_awaited_once()
    assert message.answer.await_args.kwargs["reply_markup"] == gender_keyboard()


@pytest.mark.anyio
async def test_onboarding_gender_female_button() -> None:
    state = await _fsm_context()
    await state.set_state(OnboardingStates.gender)

    message = AsyncMock()
    message.text = BTN_GENDER_FEMALE
    message.answer = AsyncMock()

    await onboarding_gender(message, state)

    data = await state.get_data()
    assert data["gender"] == GENDER_FEMALE
