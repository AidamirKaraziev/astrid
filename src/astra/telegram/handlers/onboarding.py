"""Этап 1: онбординг — сбор данных и регистрация (handlers FSM)."""

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from astra.telegram.handlers.places import start_birth_place_step
from astra.telegram.keyboards import gender_keyboard
from astra.telegram.states import OnboardingStates
from astra.telegram.utils import parse_birth_date
from astra.users.gender import normalize_gender

router = Router(name="onboarding")


@router.message(OnboardingStates.gender)
async def onboarding_gender(message: Message, state: FSMContext) -> None:
    gender = normalize_gender(message.text or "")
    if gender is None:
        await message.answer(
            "Выбери пол кнопкой ниже 👇",
            reply_markup=gender_keyboard(),
        )
        return

    await state.update_data(gender=gender)
    await state.set_state(OnboardingStates.birth_date)
    await message.answer(
        "📅 Укажи дату рождения в формате <b>ДД.ММ.ГГГГ</b>\n"
        "Например: <code>15.03.1990</code>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(OnboardingStates.birth_date)
async def onboarding_birth_date(message: Message, state: FSMContext) -> None:
    parsed = parse_birth_date(message.text or "")
    if parsed is None:
        await message.answer("Не могу разобрать дату. Попробуй ещё раз: ДД.ММ.ГГГГ")
        return
    await state.update_data(birth_date=parsed.isoformat())
    await start_birth_place_step(message, state)
