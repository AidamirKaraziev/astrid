"""FSM разбора натальной карты: время рождения (если нет) → подтверждение → очередь."""

from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.observability import Event, get_logger
from astra.services.natal_report_service import (
    NatalRequestStatus,
    create_natal_report_for_user,
    person_subtitle,
    request_natal_report,
)
from astra.telegram.button_texts import BTN_NATAL
from astra.telegram.keyboards import main_menu_keyboard
from astra.telegram.progress import (
    NatalStage,
    current_progress_message_id,
    natal_job_key,
    notify_natal_stage,
)
from astra.telegram.states import NatalStates
from astra.telegram.utils import parse_birth_time
from astra.users import crud as users_crud

log = get_logger(__name__)

router = Router(name="natal")

CB_NATAL_CONFIRM = "natal:confirm"
CB_NATAL_CANCEL = "natal:cancel"
CB_NATAL_TIME_UNKNOWN = "natal:time_unknown"

_NO_TIME_WARNING = (
    "⚠️ Без времени рождения разбор будет без асцендента и домов — "
    "по положению планет в знаках и аспектам. Это честнее, чем гадать."
)


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✨ Составить разбор", callback_data=CB_NATAL_CONFIRM)],
            [InlineKeyboardButton(text="Отмена", callback_data=CB_NATAL_CANCEL)],
        ],
    )


def _time_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤷 Не знаю время", callback_data=CB_NATAL_TIME_UNKNOWN)],
            [InlineKeyboardButton(text="Отмена", callback_data=CB_NATAL_CANCEL)],
        ],
    )


async def _require_user(message: Message, session: AsyncSession):
    if message.from_user is None:
        return None
    user = await users_crud.get_user_by_telegram_id(session, message.from_user.id)
    if user is None or not user.onboarding_completed or user.profile is None:
        await message.answer("Сначала пройди регистрацию: /start")
        return None
    return user


async def _show_confirm(message: Message, state: FSMContext, user) -> None:  # noqa: ANN001
    profile = user.profile
    subtitle = person_subtitle(profile.birth_date, profile.birth_time, profile.birth_place)
    lines = [
        "🌌 <b>Разбор натальной карты</b>",
        "",
        f"<b>{profile.display_name}</b>",
        subtitle,
        "",
        "В разборе: колесо карты, ядро личности, сильные стороны,",
        "сферы жизни, кармический вектор и практикум — PDF на ~14 страниц.",
    ]
    if profile.birth_time is None:
        lines += ["", _NO_TIME_WARNING]
    await state.set_state(NatalStates.confirm)
    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=_confirm_keyboard(),
    )


@router.message(F.text == BTN_NATAL)
async def start_natal(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user = await _require_user(message, session)
    if user is None:
        return
    await state.clear()
    if user.profile.birth_time is None:
        await state.set_state(NatalStates.collect_birth_time)
        await message.answer(
            "🌌 <b>Разбор натальной карты</b>\n\n"
            "Для асцендента и домов нужно время рождения.\n"
            "Напиши его в формате <b>14:30</b> — или нажми «Не знаю».",
            parse_mode="HTML",
            reply_markup=_time_keyboard(),
        )
        return
    await _show_confirm(message, state, user)


@router.message(NatalStates.collect_birth_time)
async def collect_birth_time(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user = await _require_user(message, session)
    if user is None:
        return
    parsed = parse_birth_time(message.text or "")
    if parsed is None:
        await message.answer("Не разобрала время. Формат: 14:30 — или нажми «Не знаю» выше.")
        return
    birth_dt = datetime.combine(user.profile.birth_date, parsed)
    await users_crud.update_profile(session, user.profile, birth_time=birth_dt)
    await session.commit()
    await _show_confirm(message, state, user)


@router.callback_query(F.data == CB_NATAL_TIME_UNKNOWN, NatalStates.collect_birth_time)
async def cb_time_unknown(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None or callback.from_user is None:
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None or user.profile is None:
        return
    await _show_confirm(callback.message, state, user)


@router.callback_query(F.data == CB_NATAL_CANCEL)
async def cb_natal_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.answer("Разбор отменён.", reply_markup=main_menu_keyboard())


@router.callback_query(F.data == CB_NATAL_CONFIRM, NatalStates.confirm)
async def cb_natal_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None or user.profile is None:
        await callback.answer("Сначала: /start", show_alert=True)
        return

    try:
        report = await create_natal_report_for_user(session, user)
        await session.commit()
        outcome = await request_natal_report(session, report.id)
    except Exception:
        log.exception(Event.NATAL_REPORT_MISSING, reason="create_failed")
        await callback.message.answer(
            "Не получилось создать разбор. Попробуй позже.",
            reply_markup=main_menu_keyboard(),
        )
        await state.clear()
        await callback.answer()
        return

    await state.clear()
    if outcome.status == NatalRequestStatus.FAILED:
        await callback.message.answer(
            "Не получилось запустить генерацию. Попробуй позже.",
            reply_markup=main_menu_keyboard(),
        )
    elif outcome.status == NatalRequestStatus.IN_PROGRESS:
        job_key = natal_job_key(report.id)
        if await current_progress_message_id(user.id, job_key) is None:
            await notify_natal_stage(
                callback.message.chat.id,
                user.id,
                report.id,
                NatalStage.STARTED,
            )
        await callback.message.answer(
            "Разбор уже готовится — пришлю сюда, как только будет готов ✨",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await notify_natal_stage(
            callback.message.chat.id,
            user.id,
            report.id,
            NatalStage.STARTED,
        )
        await callback.message.answer(
            "Приняла твою карту в работу — скоро пришлю разбор ✨",
            reply_markup=main_menu_keyboard(),
        )
    await callback.answer()
