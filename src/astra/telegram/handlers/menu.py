from datetime import datetime
from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.referrals.getters import get_referral_stats
from astra.services.points_service import register_daily_activity
from astra.services.prediction_service import get_or_create_today_prediction
from astra.telegram.keyboards import main_menu_keyboard, profile_menu_keyboard, share_keyboard
from astra.telegram.states import ProfileStates
from astra.telegram.utils import parse_birth_time
from astra.users import crud as users_crud
from astra.users.getters import profile_to_read

router = Router(name="menu")


async def _get_user(session: AsyncSession, message: Message):
    if message.from_user is None:
        return None
    return await users_crud.get_user_by_telegram_id(session, message.from_user.id)


@router.callback_query(F.data == "menu:home")
async def cb_menu_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Главное меню ✨", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.message(F.text == "🔮 Предсказание на сегодня")
async def today_prediction(message: Message, session: AsyncSession) -> None:
    user = await _get_user(session, message)
    if user is None or not user.onboarding_completed or user.profile is None:
        await message.answer("Сначала пройди регистрацию: /start")
        return
    await register_daily_activity(session, user)
    prediction = await get_or_create_today_prediction(session, user, user.profile)
    await message.answer(prediction.text, parse_mode="HTML")


@router.message(F.text == "⭐ Баллы")
async def show_points(message: Message, session: AsyncSession) -> None:
    user = await _get_user(session, message)
    if user is None:
        await message.answer("Сначала: /start")
        return
    await register_daily_activity(session, user)
    await message.answer(
        f"⭐ Баллы: <b>{user.points}</b>\n"
        f"🔥 Серия: <b>{user.streak_current}</b> дн. (рекорд: {user.streak_best})\n\n"
        "<i>Баллами можно будет оплачивать платные разборы — скоро.</i>",
        parse_mode="HTML",
    )


@router.message(F.text == "🎁 Пригласить друга")
async def invite_friend(message: Message, session: AsyncSession) -> None:
    user = await _get_user(session, message)
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
    user = await _get_user(session, message)
    if user is None or user.profile is None:
        await message.answer("Сначала: /start")
        return
    p = profile_to_read(user.profile)
    time_str = p.birth_time.strftime("%H:%M") if p.birth_time else "не указано"
    place_str = p.birth_place or "не указано"
    await message.answer(
        f"👤 <b>{p.display_name}</b>\n"
        f"📅 Дата: {p.birth_date.strftime('%d.%m.%Y')}\n"
        f"🕐 Время: {time_str}\n"
        f"📍 Место: {place_str}\n"
        f"🌍 Город: {p.city} ({p.timezone})\n\n"
        f"📊 Точность: <b>{p.accuracy_percent}%</b>\n"
        f"<i>{p.accuracy_hint}</i>",
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
    user = await _get_user(session, message)
    if user is None or user.profile is None:
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer("Имя не может быть пустым.")
        return
    await users_crud.update_profile(session, user.profile, display_name=name)
    await state.clear()
    await message.answer(f"Имя обновлено: {name} ✨", reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "profile:time")
async def cb_edit_time(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileStates.edit_birth_time)
    if callback.message:
        await callback.message.answer("Введи время рождения в формате ЧЧ:ММ (например 14:30):")
    await callback.answer()


@router.message(ProfileStates.edit_birth_time)
async def save_birth_time(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user = await _get_user(session, message)
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
        f"Время сохранено ✨\nТочность теперь: <b>{p.accuracy_percent}%</b>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(F.data == "profile:place")
async def cb_edit_place(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileStates.edit_birth_place)
    if callback.message:
        await callback.message.answer("Введи место рождения (город):")
    await callback.answer()


@router.message(ProfileStates.edit_birth_place)
async def save_birth_place(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user = await _get_user(session, message)
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
        f"Место сохранено ✨\nТочность теперь: <b>{p.accuracy_percent}%</b>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
