"""Кнопки главного меню прерывают активный FSM-сценарий.

Флоу-роутеры (совместимость, натал, таро…) ловят свободный текст своими
состояниями, а роутеры кнопок подключены после них — поэтому «🔮 Карты Таро»
или «🔙 Назад», нажатые посреди сценария, записывались как имя/дата/вопрос.

Этот роутер подключается раньше всех флоу-роутеров и срабатывает только при
активном состоянии: текст кнопки меню означает «выйти из сценария и перейти
в раздел». Без состояния роутер молчит — работает обычная маршрутизация.
Онбординг не прерываем: регистрацию нужно закончить.
"""

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.telegram.button_texts import (
    BTN_ASK_ASTRID,
    BTN_BACK_MENU,
    BTN_BACK_MENU_LEGACY,
    BTN_COMPATIBILITY,
    BTN_HELP,
    BTN_INVITE,
    BTN_NATAL,
    BTN_PROFILE,
    BTN_TAROT,
    BTN_WHEEL,
    COMING_SOON_TEXT,
    PAID_PRODUCT_BUTTONS,
)
from astra.telegram.handlers.ask_astrid import open_ask_hub
from astra.telegram.handlers.catalog import back_to_main_menu, open_tarot_menu
from astra.telegram.handlers.support import open_support_hub
from astra.telegram.handlers.compatibility import start_compatibility
from astra.telegram.handlers.day_card import LEGACY_BUTTONS, legacy_button
from astra.telegram.handlers.menu import invite_friend, show_profile
from astra.telegram.handlers.natal import start_natal
from astra.telegram.handlers.tarot_spreads import SPREAD_BUTTONS, spread_button
from astra.telegram.handlers.wheel import open_wheel
from astra.telegram.states import (
    AiChatStates,
    BirthDataStates,
    CompatibilityStates,
    NatalStates,
    PeopleStates,
    ProfileStates,
    SupportStates,
    TarotStates,
)

router = Router(name="navigation")

# Онбординга здесь нет намеренно: до конца регистрации кнопки меню не работают.
INTERRUPTIBLE_STATE_GROUPS = (
    AiChatStates,
    # Добор данных рождения: человек уже зарегистрирован и просто открыл
    # продукт. Захотел вместо разбора покрутить колесо — это его право, и
    # ответ «не могу разобрать дату» на нажатие кнопки меню был бы тупиком.
    BirthDataStates,
    CompatibilityStates,
    NatalStates,
    PeopleStates,
    ProfileStates,
    SupportStates,
    TarotStates,
)

router.message.filter(StateFilter(*INTERRUPTIBLE_STATE_GROUPS))

_PAID_STUB_BUTTONS = frozenset(PAID_PRODUCT_BUTTONS) - {BTN_TAROT, BTN_COMPATIBILITY, BTN_NATAL}


@router.message(F.text.in_({BTN_BACK_MENU, BTN_BACK_MENU_LEGACY}))
async def nav_back_to_menu(message: Message, state: FSMContext) -> None:
    await back_to_main_menu(message, state)


@router.message(F.text == BTN_TAROT)
async def nav_tarot_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await open_tarot_menu(message)


@router.message(F.text.in_(SPREAD_BUTTONS))
async def nav_tarot_spread(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await spread_button(message, state, session)


@router.message(F.text == BTN_WHEEL)
async def nav_wheel(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await open_wheel(message, state, session)


@router.message(F.text == BTN_COMPATIBILITY)
async def nav_compatibility(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await start_compatibility(message, state, session)


@router.message(F.text == BTN_NATAL)
async def nav_natal(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await start_natal(message, state, session)


@router.message(F.text == BTN_ASK_ASTRID)
async def nav_ask_astrid(message: Message, state: FSMContext) -> None:
    await state.clear()
    await open_ask_hub(message)


@router.message(F.text == BTN_HELP)
async def nav_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await open_support_hub(message)


@router.message(F.text == BTN_PROFILE)
async def nav_profile(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    await show_profile(message, session)


@router.message(F.text == BTN_INVITE)
async def nav_invite(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    await invite_friend(message, session)


@router.message(F.text.in_(LEGACY_BUTTONS))
async def nav_legacy_button(message: Message, state: FSMContext) -> None:
    # Удалённые кнопки меню (предсказание, чат с Астрид) прерывают сценарий.
    await state.clear()
    await legacy_button(message)


@router.message(F.text.in_(_PAID_STUB_BUTTONS))
async def nav_paid_stub(message: Message) -> None:
    # Заглушка не ведёт в раздел — сценарий продолжается, состояние не трогаем.
    await message.answer(COMING_SOON_TEXT)
