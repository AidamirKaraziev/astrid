"""Совместимость: временная заглушка — PDF синастрии в чат."""

from __future__ import annotations

import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.types import FSInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.services.compatibility_pdf_service import (
    STUB_PDF_FILENAME,
    render_stub_compatibility_pdf,
)
from astra.telegram.button_texts import BTN_COMPATIBILITY
from astra.telegram.keyboards import main_menu_keyboard, prediction_followup_keyboard
from astra.telegram.profile_gender_prompt import prompt_gender_if_missing
from astra.users import crud as users_crud

logger = logging.getLogger(__name__)

router = Router(name="compatibility_preview")

COMPATIBILITY_PDF_IN_PROGRESS = "Собираю PDF совместимости… ✨"
COMPATIBILITY_PDF_CAPTION = (
    "💕 <b>Синастрия</b>\n"
    "Временное превью на паре Айдамир × Анжела — скоро будет с твоими данными."
)
COMPATIBILITY_PDF_FAILED = "Не получилось собрать PDF. Попробуй ещё раз чуть позже."


@router.message(F.text == BTN_COMPATIBILITY)
async def compatibility_pdf_stub(message: Message, session: AsyncSession) -> None:
    """Заглушка: эталонный JSON → PDF → документ в чат."""
    if message.from_user is None:
        return

    user = await users_crud.get_user_by_telegram_id(session, message.from_user.id)
    if user is None or not user.onboarding_completed or user.profile is None:
        await message.answer("Сначала пройди регистрацию: /start")
        return

    if not await prompt_gender_if_missing(message, user.profile):
        return

    await message.answer(COMPATIBILITY_PDF_IN_PROGRESS)

    pdf_path: Path | None = None
    try:
        pdf_path = render_stub_compatibility_pdf()
        document = FSInputFile(pdf_path, filename=STUB_PDF_FILENAME)
        await message.answer_document(
            document,
            caption=COMPATIBILITY_PDF_CAPTION,
            parse_mode="HTML",
            reply_markup=prediction_followup_keyboard(),
        )
    except Exception:
        logger.exception("Compatibility PDF stub failed for user %s", user.id)
        await message.answer(
            COMPATIBILITY_PDF_FAILED,
            reply_markup=main_menu_keyboard(),
        )
    finally:
        if pdf_path is not None:
            pdf_path.unlink(missing_ok=True)
