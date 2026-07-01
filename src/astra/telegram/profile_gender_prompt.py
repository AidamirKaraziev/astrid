"""Запрос пола у пользователей с незаполненным profile.gender."""

from __future__ import annotations

from aiogram.types import Message

from astra.telegram.keyboards import profile_gender_inline_keyboard
from astra.users.models import Profile

GENDER_PROMPT_TEXT = (
    "Чтобы формулировки в разборе были точнее, укажи свой пол 👇"
)
GENDER_SAVED_TEXT = "Пол сохранён: {label} ✨ Теперь разборы будут персональнее."


def profile_needs_gender(profile: Profile | None) -> bool:
    return profile is not None and not profile.gender


async def prompt_gender_if_missing(message: Message, profile: Profile | None) -> bool:
    """True — пол уже есть; False — отправили запрос выбора."""
    if not profile_needs_gender(profile):
        return True
    await message.answer(
        GENDER_PROMPT_TEXT,
        reply_markup=profile_gender_inline_keyboard(),
    )
    return False
