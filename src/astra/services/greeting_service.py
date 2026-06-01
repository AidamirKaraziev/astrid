"""Этап 2: приветствие после регистрации — сообщение, меню, предсказание в фоне."""

from __future__ import annotations

import logging

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from astra.services.prediction_delivery_service import enqueue_first_prediction_after_registration
from astra.telegram.keyboards import main_menu_keyboard
from astra.users.models import User

logger = logging.getLogger(__name__)

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
    logger.info("greeting phase completed for user %s", user.id)
