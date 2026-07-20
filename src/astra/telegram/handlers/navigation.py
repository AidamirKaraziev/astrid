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

from astra.core.config import get_settings
from astra.telegram.button_texts import (
    BTN_ASK_ASTRID,
    BTN_ASK_ASTRID_LEGACY,
    BTN_BACK_MENU,
    BTN_BACK_MENU_LEGACY,
    BTN_COMPATIBILITY,
    BTN_INVITE,
    BTN_NATAL,
    BTN_PREDICTION_TODAY,
    BTN_PROFILE,
    BTN_TAROT,
    COMING_SOON_TEXT,
    PAID_PRODUCT_BUTTONS,
)
from astra.telegram.handlers.catalog import back_to_main_menu, open_tarot_menu
from astra.telegram.handlers.compatibility import start_compatibility
from astra.telegram.handlers.menu import invite_friend, show_profile, today_prediction
from astra.telegram.handlers.natal import start_natal
from astra.telegram.handlers.tarot_spreads import SPREAD_BUTTONS, spread_button
from astra.telegram.states import (
    AiChatStates,
    CompatibilityStates,
    NatalStates,
    PeopleStates,
    ProfileStates,
    TarotStates,
)

router = Router(name="navigation")

# Онбординга здесь нет намеренно: до конца регистрации кнопки меню не работают.
INTERRUPTIBLE_STATE_GROUPS = (
    AiChatStates,
    CompatibilityStates,
    NatalStates,
    PeopleStates,
    ProfileStates,
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


@router.message(F.text == BTN_COMPATIBILITY)
async def nav_compatibility(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await start_compatibility(message, state, session)


@router.message(F.text == BTN_NATAL)
async def nav_natal(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await start_natal(message, state, session)


@router.message(F.text == BTN_PREDICTION_TODAY)
async def nav_prediction(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    await today_prediction(message, session)


@router.message(F.text == BTN_PROFILE)
async def nav_profile(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    await show_profile(message, session)


@router.message(F.text == BTN_INVITE)
async def nav_invite(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    await invite_friend(message, session)


@router.message(F.text.in_({BTN_ASK_ASTRID, BTN_ASK_ASTRID_LEGACY}))
async def nav_ask_astrid(message: Message, state: FSMContext) -> None:
    if not get_settings().ai_chat_enabled:
        await message.answer(COMING_SOON_TEXT)
        return
    # Ленивый импорт: модуль тянет LLM-стек и грузится только при включённом чате.
    from astra.telegram.ai_chat.handler import ai_chat_enter

    await state.clear()
    await ai_chat_enter(message, state)


@router.message(F.text.in_(_PAID_STUB_BUTTONS))
async def nav_paid_stub(message: Message) -> None:
    # Заглушка не ведёт в раздел — сценарий продолжается, состояние не трогаем.
    await message.answer(COMING_SOON_TEXT)
