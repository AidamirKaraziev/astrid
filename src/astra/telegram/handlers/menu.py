import html
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.astro.birth_time import wall_clock_at, with_birth_date
from astra.referrals.getters import get_referral_stats
from astra.telegram.handlers.places import (
    start_profile_birth_place_step,
    start_profile_notification_place_step,
)
from astra.telegram.button_texts import (
    BTN_INVITE,
    BTN_PROFILE,
    BTN_TIME_UNKNOWN,
    CB_PROFILE_BACK,
    CB_PROFILE_EDIT,
    CB_PROFILE_TIME_UNKNOWN,
)
from astra.telegram.keyboards import (
    main_menu_keyboard,
    profile_birth_time_keyboard,
    profile_edit_keyboard,
    profile_gender_inline_keyboard,
    profile_menu_keyboard,
    share_keyboard,
)
from astra.telegram.profile_portrait import build_portrait_text
from astra.telegram.profile_gender_prompt import GENDER_SAVED_TEXT
from astra.telegram.states import ProfileStates
from astra.telegram.utils import parse_birth_date, parse_birth_time
from astra.users import crud as users_crud
from astra.telegram.profile_text import format_profile_card
from astra.users.gender import (
    GENDER_FEMALE,
    GENDER_MALE,
    gender_display_label,
    normalize_gender,
)
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


async def _send_portrait(message: Message, session: AsyncSession, user) -> None:  # noqa: ANN001
    """Показать портрет после правки данных о рождении.

    Смысл правки — в том, что меняется в карте: вписал время — увидел
    асцендент и дома. Без этого человек читает «сохранено» и не понимает,
    что именно он получил.
    """
    await message.answer(
        await build_portrait_text(session, user, user.profile),
        parse_mode="HTML",
        reply_markup=profile_menu_keyboard(),
    )


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
        await message.answer("Сначала давай познакомимся — жми /start ✨")
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
        await message.answer("Сначала давай познакомимся — жми /start ✨")
        return
    await message.answer(
        await build_portrait_text(session, user, user.profile),
        parse_mode="HTML",
        reply_markup=profile_menu_keyboard(),
    )


@router.callback_query(F.data == CB_PROFILE_BACK)
async def cb_profile_back(callback: CallbackQuery, session: AsyncSession) -> None:
    """Возврат к портрету — из экрана правки и из архивов разборов."""
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    user = await _get_user(session, callback.from_user.id)
    if user is None or user.profile is None:
        await callback.answer("Сначала давай познакомимся — жми /start ✨", show_alert=True)
        return
    await callback.message.answer(
        await build_portrait_text(session, user, user.profile),
        parse_mode="HTML",
        reply_markup=profile_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == CB_PROFILE_EDIT)
async def cb_profile_edit(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    user = await _get_user(session, callback.from_user.id)
    if user is None or user.profile is None:
        await callback.answer("Сначала давай познакомимся — жми /start ✨", show_alert=True)
        return
    await callback.message.answer(
        format_profile_card(user, user.profile),
        parse_mode="HTML",
        reply_markup=profile_edit_keyboard(),
    )
    await callback.answer()


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
        await callback.answer("Сначала давай познакомимся — жми /start ✨", show_alert=True)
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
            "🌌 Напиши новую дату рождения цифрами\n"
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
        await message.answer("Не разобрала дату. Напиши цифрами — например 15.03.1990")
        return

    update_fields: dict[str, object] = {"birth_date": parsed}
    moved = with_birth_date(user.profile.birth_time, parsed)
    if moved is not None:
        update_fields["birth_time"] = moved

    await users_crud.update_profile(session, user.profile, **update_fields)
    await state.clear()
    await message.answer(
        f"Дата сохранена: {parsed.strftime('%d.%m.%Y')} ✨\n"
        "Предсказание на сегодня обновится при следующем запросе.",
    )
    await _send_portrait(message, session, user)


@router.callback_query(F.data == "profile:time")
async def cb_edit_time(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileStates.edit_birth_time)
    if callback.message:
        await callback.message.answer(
            "🕐 Напиши время рождения — например <code>14:30</code>\n"
            f"Не знаешь — нажми «{BTN_TIME_UNKNOWN}», посчитаю без него.",
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
        await callback.answer("Сначала давай познакомимся — жми /start ✨", show_alert=True)
        return

    had_time = user.profile.birth_time is not None
    await users_crud.clear_birth_time(session, user.profile)
    await state.clear()
    head = "Убрала время рождения ✨" if had_time else "Хорошо, обойдусь без времени ✨"
    # Процент точности здесь не показываем: человек не виноват, что не знает
    # своего времени, и цифра читалась бы как приговор профилю.
    await callback.message.answer(
        f"{head}\n\n"
        "Многие его не знают — считаю по знакам и аспектам. "
        "Найдётся время — впиши, добавлю асцендент и дома.",
        parse_mode="HTML",
    )
    await _send_portrait(callback.message, session, user)
    await callback.answer()


@router.message(ProfileStates.edit_birth_time)
async def save_birth_time(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user = await _get_user_from_message(session, message)
    if user is None or user.profile is None:
        return
    parsed = parse_birth_time(message.text or "")
    if parsed is None:
        await message.answer(f"Не разобрала время. Напиши как 14:30 — или нажми «{BTN_TIME_UNKNOWN}».")
        return
    if user.profile.birth_date is None:
        # Время рождения хранится настенными часами на дату рождения: без
        # даты его некуда положить.
        await message.answer("Сначала добавь дату рождения — время привязывается к ней 📅")
        await state.clear()
        return
    birth_dt = wall_clock_at(user.profile.birth_date, parsed)
    await users_crud.update_profile(session, user.profile, birth_time=birth_dt)
    await state.clear()
    p = profile_to_read(user.profile)
    await message.answer(
        f"Время сохранено ✨\nТочность теперь: <b>{p.accuracy_percent}%</b>\n"
        "Предсказание на сегодня обновится при следующем запросе.",
        parse_mode="HTML",
    )
    await _send_portrait(message, session, user)


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
        await callback.answer("Сначала давай познакомимся — жми /start ✨", show_alert=True)
        return
    await start_profile_notification_place_step(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "profile:place")
async def cb_edit_place(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Правка места рождения идёт через справочник, а не свободным текстом.

    Раньше введённое название сохранялось как есть, а координаты подбирались
    молча по первому совпадению: человек писал «Иваново» и не знал, какое из
    них легло в его карту.
    """
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    user = await _get_user(session, callback.from_user.id)
    if user is None or user.profile is None:
        await callback.answer("Сначала давай познакомимся — жми /start ✨", show_alert=True)
        return
    await start_profile_birth_place_step(
        callback.message,
        state,
        gender=normalize_gender(user.profile.gender),
    )
    await callback.answer()


async def complete_profile_birth_place(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    *,
    place,  # noqa: ANN001 — PlaceRead
    actor_telegram_id: int,
) -> None:
    """Вызывается из places после выбора населённого пункта."""
    user = await _get_user(session, actor_telegram_id)
    if user is None or user.profile is None:
        await message.answer("Сначала давай познакомимся — жми /start ✨")
        return

    updates: dict[str, object] = {
        "birth_place_id": place.id,
        "birth_place": place.display_name,
    }
    # Тот же уговор, что и при доборе данных: пока человек не выбрал город
    # уведомлений сам, рассылка идёт по месту рождения — иначе предсказание
    # уходило бы в 09:00 по Москве тому, кто живёт во Владивостоке.
    if user.profile.notification_place_id is None:
        updates["city"] = place.display_name
        updates["timezone"] = place.timezone

    await users_crud.update_profile(session, user.profile, **updates)
    await state.clear()
    p = profile_to_read(user.profile)
    await message.answer(
        f"Место рождения: <b>{html.escape(place.display_name)}</b> ✨\n"
        f"Точность теперь: <b>{p.accuracy_percent}%</b>\n"
        "Предсказание на сегодня обновится при следующем запросе.",
        parse_mode="HTML",
    )
    await _send_portrait(message, session, user)
