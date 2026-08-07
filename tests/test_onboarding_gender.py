"""Шаг пола — последний в онбординге: за ним сразу регистрация.

Раньше отсюда шли к дате рождения, потом к месту, и только там человек
попадал в базу. Теперь профиль создаётся на имени и поле, а астроданные
спрашиваются у продукта, которому они нужны.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from astra.telegram.button_texts import BTN_GENDER_FEMALE, BTN_GENDER_MALE
from astra.telegram.handlers import onboarding as onboarding_handlers
from astra.telegram.handlers.onboarding import complete_short_onboarding, onboarding_gender
from astra.telegram.keyboards import gender_keyboard
from astra.telegram.states import OnboardingStates
from astra.users.gender import GENDER_FEMALE, GENDER_MALE


async def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=2, user_id=3)
    return FSMContext(storage=storage, key=key)


@pytest.mark.anyio
async def test_onboarding_gender_saves_and_registers() -> None:
    state = await _fsm_context()
    await state.set_state(OnboardingStates.gender)

    message = AsyncMock()
    message.text = BTN_GENDER_MALE
    message.answer = AsyncMock()

    with patch.object(onboarding_handlers, "complete_short_onboarding", new=AsyncMock()) as done:
        await onboarding_gender(message, state, AsyncMock())

    data = await state.get_data()
    assert data["gender"] == GENDER_MALE
    done.assert_awaited_once()


@pytest.mark.anyio
async def test_onboarding_gender_invalid_input_reprompts() -> None:
    state = await _fsm_context()
    await state.set_state(OnboardingStates.gender)

    message = AsyncMock()
    message.text = "не знаю"
    message.answer = AsyncMock()

    await onboarding_gender(message, state, AsyncMock())

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

    with patch.object(onboarding_handlers, "complete_short_onboarding", new=AsyncMock()):
        await onboarding_gender(message, state, AsyncMock())

    data = await state.get_data()
    assert data["gender"] == GENDER_FEMALE


@pytest.mark.anyio
async def test_registration_completes_without_birth_data() -> None:
    """Профиль создаётся по имени и полу — без даты, времени и места."""
    state = await _fsm_context()
    user_id = uuid4()
    await state.set_data(
        {
            "user_id": str(user_id),
            "display_name": "Анна",
            "gender": GENDER_FEMALE,
        },
    )

    message = AsyncMock()
    session = AsyncMock()
    user = AsyncMock()

    with (
        patch.object(onboarding_handlers.users_crud, "get_user_by_id", new=AsyncMock(return_value=user)),
        patch.object(onboarding_handlers, "run_registration_phase", new=AsyncMock()) as register,
        patch.object(onboarding_handlers, "run_greeting_phase", new=AsyncMock()) as greet,
    ):
        await complete_short_onboarding(message, state, session)

    register.assert_awaited_once()
    reg = register.await_args.args[2]
    assert reg.display_name == "Анна"
    assert reg.birth_date is None
    assert reg.birth_place_id is None
    greet.assert_awaited_once()
