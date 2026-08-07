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

# Короткий онбординг: даты рождения нет, предсказание построить не от чего.
# Обещать его здесь нельзя — обещание не сбудется, и первое же впечатление
# окажется обманом. Поэтому зовём туда, что работает прямо сейчас.
REGISTRATION_SHORT_TEXT = (
    "✨ <b>Готово, будем знакомы!</b>\n\n"
    "<b>Попробуй прямо сейчас</b>\n"
    "🃏 <b>Карта дня</b> — подсказка на сегодня, бесплатно\n"
    "🎡 <b>Колесо фортуны</b> — крути и забирай подарок\n"
    "🔮 <b>Расклады Таро</b> — на отношения, на желание, три карты\n\n"
    "<b>🌌 Захочешь глубже</b>\n"
    "🌌 <b>Разбор натала</b> — твоя карта неба целиком\n"
    "💕 <b>Совместимость</b> — вы двое и что между вами\n"
    "✨ <b>Спроси Астрид</b> — ответ на личный вопрос по твоей карте\n\n"
    "<i>Для них понадобится дата рождения — спрошу, когда откроешь 💜</i>\n\n"
    "Начни с того, что интересно прямо сейчас 👇"
)


async def run_greeting_phase(message: Message, state: FSMContext, user: User) -> None:
    """Приветствие сразу после регистрации: текст, меню, фоновая генерация предсказания."""
    has_birth_data = user.profile is not None and user.profile.birth_date is not None
    await message.answer(
        REGISTRATION_COMPLETE_TEXT if has_birth_data else REGISTRATION_SHORT_TEXT,
        reply_markup=main_menu_keyboard(),
    )
    await state.clear()
    if has_birth_data:
        await enqueue_first_prediction_after_registration(user.id)
    log.info(Event.GREETING_COMPLETED, user_id=user.id, has_birth_data=has_birth_data)
