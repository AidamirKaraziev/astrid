from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.referrals.getters import get_referral_stats
from astra.telegram.handlers.places import start_profile_notification_place_step
from astra.telegram.button_texts import (
    BTN_INVITE,
    BTN_PROFILE,
    BTN_TIME_UNKNOWN,
    CB_PROFILE_TIME_UNKNOWN,
)
from astra.telegram.keyboards import (
    main_menu_keyboard,
    profile_birth_time_keyboard,
    profile_gender_inline_keyboard,
    profile_menu_keyboard,
    share_keyboard,
)
from astra.telegram.profile_gender_prompt import GENDER_SAVED_TEXT
from astra.telegram.states import ProfileStates
from astra.telegram.utils import parse_birth_date, parse_birth_time
from astra.users import crud as users_crud
from astra.telegram.profile_text import format_profile_card
from astra.users.gender import GENDER_FEMALE, GENDER_MALE, gender_display_label
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


@router.message(F.text == BTN_INVITE)
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


@router.message(F.text == BTN_PROFILE)
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


@router.callback_query(F.data == "profile:gender")
async def cb_edit_gender(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.answer(
            "Выбери пол:",
            reply_markup=profile_gender_inline_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data.in_({"profile:gender:male", "profile:gender:female"}))
async def cb_save_gender(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    user = await _get_user(session, callback.from_user.id)
    if user is None or user.profile is None:
        await callback.answer("Сначала: /start", show_alert=True)
        return

    gender = GENDER_MALE if callback.data == "profile:gender:male" else GENDER_FEMALE
    had_gender = user.profile.gender is not None
    await users_crud.update_profile(session, user.profile, gender=gender)
    label = gender_display_label(gender) or gender
    if callback.message:
        text = (
            f"Пол обновлён: {label} ✨"
            if had_gender
            else GENDER_SAVED_TEXT.format(label=label)
        )
        await callback.message.answer(
            text,
            reply_markup=main_menu_keyboard(),
        )
    await callback.answer()


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
        await callback.message.answer(
            "Введи время рождения в формате <b>ЧЧ:ММ</b> (например <code>14:30</code>).\n"
            f"Если не знаешь — нажми «{BTN_TIME_UNKNOWN}», посчитаю без него.",
            parse_mode="HTML",
            reply_markup=profile_birth_time_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == CB_PROFILE_TIME_UNKNOWN)
async def cb_birth_time_unknown(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Сброс времени рождения: лучше без него, чем с выдуманным."""
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    user = await _get_user(session, callback.from_user.id)
    if user is None or user.profile is None:
        await callback.answer("Сначала: /start", show_alert=True)
        return

    had_time = user.profile.birth_time is not None
    await users_crud.clear_birth_time(session, user.profile)
    await state.clear()
    p = profile_to_read(user.profile)
    head = "Убрала время рождения ✨" if had_time else "Хорошо, обойдусь без времени ✨"
    await callback.message.answer(
        f"{head}\nТочность теперь: <b>{p.accuracy_percent}%</b>\n\n"
        "Считаю по знакам и аспектам — без асцендента и домов. "
        "Вспомнишь время — впиши, стану точнее.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


@router.message(ProfileStates.edit_birth_time)
async def save_birth_time(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user = await _get_user_from_message(session, message)
    if user is None or user.profile is None:
        return
    parsed = parse_birth_time(message.text or "")
    if parsed is None:
        await message.answer(f"Не разобрал время. Формат: 14:30 — или нажми «{BTN_TIME_UNKNOWN}».")
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
