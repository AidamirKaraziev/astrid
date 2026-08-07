"""Кнопки главного меню прерывают FSM-сценарий, а не записываются как ввод.

Баг: «🔮 Карты Таро», нажатая посреди совместимости, сохранялась как имя
первого человека, потому что flow-роутеры подключены раньше кнопочных.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from astra.telegram.button_texts import BTN_TAROT, COMING_SOON_TEXT
from astra.telegram.handlers.navigation import (
    INTERRUPTIBLE_STATE_GROUPS,
    nav_back_to_menu,
    nav_paid_stub,
    nav_legacy_button,
    nav_tarot_menu,
)
from astra.telegram.states import (
    BirthDataStates,
    CompatibilityStates,
    OnboardingStates,
    TarotStates,
)


async def _fsm() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=2, user_id=3))


def _message(text: str = BTN_TAROT) -> AsyncMock:
    message = AsyncMock()
    message.text = text
    message.answer = AsyncMock()
    return message


@pytest.mark.asyncio
async def test_router_filter_matches_flow_states_but_not_onboarding() -> None:
    state_filter = StateFilter(*INTERRUPTIBLE_STATE_GROUPS)
    obj = MagicMock()
    assert await state_filter(obj, raw_state=CompatibilityStates.collect_name.state)
    assert await state_filter(obj, raw_state=TarotStates.waiting_question.state)
    # Добор данных прерывать можно: человек уже зарегистрирован.
    assert await state_filter(obj, raw_state=BirthDataStates.date.state)
    # без активного состояния и в онбординге роутер молчит: там регистрация,
    # и уйти из неё на середине человеку предлагать нельзя
    assert not await state_filter(obj, raw_state=None)
    assert not await state_filter(obj, raw_state=OnboardingStates.gender.state)


@pytest.mark.asyncio
async def test_tarot_button_clears_state_and_opens_menu() -> None:
    state = await _fsm()
    await state.set_state(CompatibilityStates.collect_name)
    await state.update_data(collecting="person_a")
    message = _message(BTN_TAROT)

    with patch(
        "astra.telegram.handlers.navigation.open_tarot_menu",
        new=AsyncMock(),
    ) as open_menu:
        await nav_tarot_menu(message, state)

    assert await state.get_state() is None
    assert await state.get_data() == {}
    open_menu.assert_awaited_once_with(message)


@pytest.mark.asyncio
async def test_back_button_clears_state_and_shows_main_menu() -> None:
    state = await _fsm()
    await state.set_state(CompatibilityStates.collect_birth_date)
    message = _message("🔙 Назад")

    await nav_back_to_menu(message, state)

    assert await state.get_state() is None
    text = message.answer.await_args.args[0]
    assert "Главное меню" in text


@pytest.mark.asyncio
async def test_legacy_prediction_button_clears_state_and_explains() -> None:
    state = await _fsm()
    await state.set_state(CompatibilityStates.collect_name)
    message = _message("🔮 Предсказание на сегодня")

    await nav_legacy_button(message, state)

    assert await state.get_state() is None
    assert "карту дня" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_paid_stub_answers_without_breaking_flow() -> None:
    message = _message("📅 Прогноз на месяц")

    await nav_paid_stub(message)

    message.answer.assert_awaited_once_with(COMING_SOON_TEXT)


@pytest.mark.asyncio
async def test_navigation_router_registered_before_flow_routers() -> None:
    # Диспетчер один на процесс: роутеры — модульные синглтоны и ко второму
    # `Dispatcher` не приклеиваются (см. tests/fake_telegram.py).
    from fake_telegram import get_shared_dispatcher

    dp = await get_shared_dispatcher()

    names = [r.name for r in dp.sub_routers]
    assert "navigation" in names
    nav_index = names.index("navigation")
    for flow in ("places", "menu", "compatibility", "people", "natal", "tarot_spreads", "catalog"):
        assert nav_index < names.index(flow), f"navigation должен идти раньше {flow}"
