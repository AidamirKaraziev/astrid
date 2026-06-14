from datetime import datetime
from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.referrals.getters import get_referral_stats
from astra.services.points_service import register_daily_activity
from astra.services.prediction_service import (
    PREDICTION_IN_PROGRESS_TEXT,
    PredictionRequestStatus,
    format_prediction_for_user,
    request_today_prediction,
)
from astra.telegram.handlers.places import start_profile_notification_place_step
from astra.telegram.keyboards import main_menu_keyboard, profile_menu_keyboard, share_keyboard
from astra.telegram.states import ProfileStates
from astra.telegram.utils import parse_birth_date, parse_birth_time
from astra.users import crud as users_crud
from astra.telegram.profile_text import format_profile_card
from astra.users.getters import profile_to_read

router = Router(name="menu")


async def _get_user(session: AsyncSession, telegram_id: int):
    return await users_crud.get_user_by_telegram_id(session, telegram_id)


def _telegram_id_from_message(message: Message) -> int | None:
    return message.from_user.id if message.from_user else None


async def _get_user_from_message(session: AsyncSession, message: Message):
    tg_id = _telegram_id_from_message(message)
    if tg_id is None:
        return None
    return await _get_user(session, tg_id)


@router.callback_query(F.data == "menu:home")
async def cb_menu_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Главное меню ✨", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.message(F.text == "🔮 Предсказание на сегодня")
async def today_prediction(message: Message, session: AsyncSession) -> None:
    tg_id = _telegram_id_from_message(message)
    if tg_id is None:
        return
    user = await _get_user(session, tg_id)
    if user is None or not user.onboarding_completed or user.profile is None:
        await message.answer("Сначала пройди регистрацию: /start")
        return
    await register_daily_activity(session, user)
    outcome = await request_today_prediction(
        session,
        user,
        user.profile,
        allow_async=True,
    )
    if outcome.status in {
        PredictionRequestStatus.QUEUED,
        PredictionRequestStatus.IN_PROGRESS,
    }:
        await message.answer(PREDICTION_IN_PROGRESS_TEXT)
        return
    if outcome.status == PredictionRequestStatus.FAILED:
        return
    if outcome.prediction is None:
        await message.answer(PREDICTION_IN_PROGRESS_TEXT)
        return
    await message.answer(
        format_prediction_for_user(outcome.prediction, user, user.profile),
        parse_mode="HTML",
    )


@router.message(F.text == "🎁 Пригласить друга")
async def invite_friend(message: Message, session: AsyncSession) -> None:
    user = await _get_user_from_message(session, message)
    if user is None:
        await message.answer("Сначала: /start")
        return
    stats = await get_referral_stats(session, user.id)
    from urllib.parse import quote

    share_url = (
        f"https://t.me/share/url?url={stats.referral_link}"
        f"&text={quote('Попробуй Astra — магическая поддержка каждый день ✨')}"
    )
    await message.answer(
        f"🎁 Твоя ссылка:\n<code>{stats.referral_link}</code>\n\n"
        f"Приглашено: <b>{stats.invited_count}</b>\n"
        f"Заработано баллов: <b>{stats.points_earned}</b>",
        parse_mode="HTML",
        reply_markup=share_keyboard(share_url),
    )


@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message, session: AsyncSession) -> None:
    user = await _get_user_from_message(session, message)
    if user is None or user.profile is None:
        await message.answer("Сначала: /start")
        return
    await message.answer(
        format_profile_card(user, user.profile),
        parse_mode="HTML",
        reply_markup=profile_menu_keyboard(),
    )


@router.callback_query(F.data == "profile:name")
async def cb_edit_name(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileStates.edit_name)
    if callback.message:
        await callback.message.answer("Отправь новое имя:")
    await callback.answer()


@router.message(ProfileStates.edit_name)
async def save_name(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user = await _get_user_from_message(session, message)
    if user is None or user.profile is None:
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer("Имя не может быть пустым.")
        return
    await users_crud.update_profile(session, user.profile, display_name=name)
    await state.clear()
    await message.answer(f"Имя обновлено: {name} ✨", reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "profile:date")
async def cb_edit_birth_date(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileStates.edit_birth_date)
    if callback.message:
        await callback.message.answer(
            "Введи дату рождения в формате <b>ДД.ММ.ГГГГ</b>\n"
            "Например: <code>15.03.1990</code>",
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(ProfileStates.edit_birth_date)
async def save_birth_date(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user = await _get_user_from_message(session, message)
    if user is None or user.profile is None:
        return
    parsed = parse_birth_date(message.text or "")
    if parsed is None:
        await message.answer("Не разобрал дату. Формат: ДД.ММ.ГГГГ (например 15.03.1990)")
        return

    update_fields: dict[str, object] = {"birth_date": parsed}
    if user.profile.birth_time is not None:
        update_fields["birth_time"] = user.profile.birth_time.replace(
            year=parsed.year,
            month=parsed.month,
            day=parsed.day,
        )

    await users_crud.update_profile(session, user.profile, **update_fields)
    await state.clear()
    await message.answer(
        f"Дата сохранена: {parsed.strftime('%d.%m.%Y')} ✨\n"
        "Предсказание на сегодня обновится при следующем запросе.",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(F.data == "profile:time")
async def cb_edit_time(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileStates.edit_birth_time)
    if callback.message:
        await callback.message.answer("Введи время рождения в формате ЧЧ:ММ (например 14:30):")
    await callback.answer()


@router.message(ProfileStates.edit_birth_time)
async def save_birth_time(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user = await _get_user_from_message(session, message)
    if user is None or user.profile is None:
        return
    parsed = parse_birth_time(message.text or "")
    if parsed is None:
        await message.answer("Не разобрал время. Формат: 14:30")
        return
    birth_dt = datetime.combine(user.profile.birth_date, parsed)
    await users_crud.update_profile(session, user.profile, birth_time=birth_dt)
    await state.clear()
    p = profile_to_read(user.profile)
    await message.answer(
        f"Время сохранено ✨\nТочность теперь: <b>{p.accuracy_percent}%</b>\n"
        "Предсказание на сегодня обновится при следующем запросе.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(F.data == "profile:notification_city")
async def cb_edit_notification_city(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    user = await _get_user(session, callback.from_user.id)
    if user is None or user.profile is None:
        await callback.answer("Сначала: /start", show_alert=True)
        return
    await start_profile_notification_place_step(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "profile:place")
async def cb_edit_place(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileStates.edit_birth_place)
    if callback.message:
        await callback.message.answer("Введи место рождения (город):")
    await callback.answer()


@router.message(ProfileStates.edit_birth_place)
async def save_birth_place(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user = await _get_user_from_message(session, message)
    if user is None or user.profile is None:
        return
    place = (message.text or "").strip()
    if not place:
        await message.answer("Место не может быть пустым.")
        return
    await users_crud.update_profile(session, user.profile, birth_place=place)
    await state.clear()
    p = profile_to_read(user.profile)
    await message.answer(
        f"Место сохранено ✨\nТочность теперь: <b>{p.accuracy_percent}%</b>\n"
        "Предсказание на сегодня обновится при следующем запросе.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
