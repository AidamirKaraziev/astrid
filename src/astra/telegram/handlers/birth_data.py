"""Ответ человека на добор данных рождения: дата.

Место сюда не входит — у него свой модуль с поиском, регионами и страницами
(`handlers/places.py`), дублировать его нельзя. Время тоже: его спрашивает
сам продукт, объясняя, что теряется без него. Логика «что дальше и куда
вернуть» живёт в `birth_data_gate`, здесь только разбор написанного.
"""

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.telegram.birth_data_gate import save_birth_date
from astra.telegram.states import BirthDataStates
from astra.telegram.utils import parse_birth_date
from astra.users import crud as users_crud

router = Router(name="birth_data")


@router.message(BirthDataStates.date)
async def collect_birth_date(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.from_user is None:
        return
    user = await users_crud.get_user_by_telegram_id(session, message.from_user.id)
    if user is None or user.profile is None:
        await message.answer("Сначала давай познакомимся — жми /start ✨")
        await state.set_state(None)
        return

    parsed = parse_birth_date(message.text or "")
    if parsed is None:
        await message.answer(
            "Не разобрала дату. Попробуй ещё раз цифрами — "
            "например <code>15.03.1990</code>",
        )
        return

    await save_birth_date(message, state, session, user, parsed)
