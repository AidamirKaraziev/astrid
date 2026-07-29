"""Карта дня: прогноз по кнопке под утренней картой и переход к раскладам."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.observability import get_logger
from astra.services.day_card_service import FORECAST_FAILED_TEXT, build_day_forecast
from astra.telegram.button_texts import (
    BTN_ASK_ASTRID_LEGACY,
    BTN_ASK_ASTRID_LEGACY_LATIN,
    BTN_PREDICTION_TODAY_LEGACY,
    CB_DAY_CARD_FORECAST,
    CB_TAROT_SECTION,
)
from astra.telegram.handlers.catalog import open_tarot_menu
from astra.telegram.keyboards import day_forecast_followup_keyboard, main_menu_keyboard
from astra.usage import ACTION_DAY_CARD, UsageKind, record_usage
from astra.users import crud as users_crud

log = get_logger(__name__)

router = Router(name="day_card")

# Старые кнопки остались в закэшированных клавиатурах — объясняем, что изменилось.
LEGACY_BUTTONS = frozenset(
    {
        BTN_PREDICTION_TODAY_LEGACY,
        BTN_ASK_ASTRID_LEGACY,
        BTN_ASK_ASTRID_LEGACY_LATIN,
    },
)

LEGACY_REPLACED_TEXT = (
    "Теперь вместо предсказания я присылаю <b>карту дня</b> 🎴\n"
    "Она приходит утром сама — а прогноз по ней ты открываешь одной кнопкой."
)


@router.callback_query(F.data == CB_DAY_CARD_FORECAST)
async def cb_day_card_forecast(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None or user.profile is None:
        await callback.answer("Сначала: /start", show_alert=True)
        return

    await callback.answer("Читаю твой день по карте…")

    target = datetime.now(ZoneInfo(user.profile.timezone)).date()
    outcome = await build_day_forecast(session, user, target)

    if outcome.text is None:
        if outcome.failure_reason == "in_progress":
            return  # прогноз уже пишется — второе сообщение не шлём
        await callback.message.answer(FORECAST_FAILED_TEXT, parse_mode="HTML")
        return

    await record_usage(session, user, action=ACTION_DAY_CARD, kind=UsageKind.FORECAST)
    await session.commit()
    # Кнопку под картой убираем: прогноз уже открыт, повторное нажатие ни к чему.
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001 — сообщение могло устареть, это не ошибка сценария
        log.info("day_card.markup_not_cleared", user_id=str(user.id))

    await callback.message.answer(
        outcome.text,
        parse_mode="HTML",
        reply_markup=day_forecast_followup_keyboard(),
    )


@router.callback_query(F.data == CB_TAROT_SECTION)
async def cb_open_tarot_section(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await open_tarot_menu(callback.message)


@router.message(F.text.in_(LEGACY_BUTTONS))
async def legacy_button(message: Message) -> None:
    await message.answer(
        LEGACY_REPLACED_TEXT,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
