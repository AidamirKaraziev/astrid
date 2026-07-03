"""Этап 2: приветствие после регистрации — сообщение, меню, предсказание в фоне."""

from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from astra.core.observability import Event, get_logger
from astra.services.prediction_delivery_service import enqueue_first_prediction_after_registration
from astra.telegram.keyboards import main_menu_keyboard
from astra.users.models import User

log = get_logger(__name__)

REGISTRATION_COMPLETE_TEXT = (
    "Поздравляю! Регистрация завершена ♥️\n\n"
    "Мы отправили тебе предсказание на день — подожди немного 🫂"
)


async def run_greeting_phase(message: Message, state: FSMContext, user: User) -> None:
    """Приветствие сразу после регистрации: текст, меню, фоновая генерация предсказания."""
    await message.answer(
        REGISTRATION_COMPLETE_TEXT,
        reply_markup=main_menu_keyboard(),
    )
    await state.clear()
    await enqueue_first_prediction_after_registration(user.id)
    log.info(Event.GREETING_COMPLETED, user_id=user.id)
