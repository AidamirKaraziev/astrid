"""Этап 1: онбординг — сбор данных и регистрация (handlers FSM)."""

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from astra.telegram.handlers.places import start_birth_place_step
from astra.telegram.states import OnboardingStates
from astra.telegram.utils import parse_birth_date

router = Router(name="onboarding")


@router.message(OnboardingStates.birth_date)
async def onboarding_birth_date(message: Message, state: FSMContext) -> None:
    parsed = parse_birth_date(message.text or "")
    if parsed is None:
        await message.answer("Не могу разобрать дату. Попробуй ещё раз: ДД.ММ.ГГГГ")
        return
    await state.update_data(birth_date=parsed.isoformat())
    await start_birth_place_step(message, state)
