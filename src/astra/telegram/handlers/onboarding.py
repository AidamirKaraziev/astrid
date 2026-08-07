"""Этап 1: онбординг — знакомство и регистрация (handlers FSM).

Онбординг спрашивает две вещи: как обращаться и какого человек пола. Дата,
время и место рождения здесь больше не собираются — они добираются тогда,
когда человек открывает продукт, которому нужны (`birth_data_gate`).

Причина простая: каждый экран между «нажал старт» и «получил ценность» стоит
людей. Пол остаётся в онбординге не ради астрологии, а ради речи: без него бот
не знает, «готова» или «готов», и это видно в первом же сообщении.
"""

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from astra.services.greeting_service import run_greeting_phase
from astra.services.onboarding_service import parse_registration_fsm, run_registration_phase
from astra.telegram.keyboards import gender_keyboard
from astra.telegram.states import OnboardingStates
from astra.users import crud as users_crud
from astra.users.gender import normalize_gender

router = Router(name="onboarding")


@router.message(OnboardingStates.gender)
async def onboarding_gender(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    gender = normalize_gender(message.text or "")
    if gender is None:
        await message.answer(
            "Выбери пол кнопкой ниже 👇",
            reply_markup=gender_keyboard(),
        )
        return

    await state.update_data(gender=gender)
    await complete_short_onboarding(message, state, session)


async def complete_short_onboarding(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Создать профиль по имени и полу и открыть человеку меню."""
    fsm_data = await state.get_data()
    reg = parse_registration_fsm(fsm_data)
    if reg is None:
        await message.answer("Что-то сбилось. Начнём заново — жми /start", reply_markup=ReplyKeyboardRemove())
        return

    user = await users_crud.get_user_by_id(session, reg.user_id)
    if user is None:
        await message.answer("Что-то сбилось. Начнём заново — жми /start", reply_markup=ReplyKeyboardRemove())
        return

    await run_registration_phase(session, user, reg)
    await session.commit()
    await run_greeting_phase(message, state, user)
