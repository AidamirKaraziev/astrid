"""«Мои люди»: просмотр, редактирование и удаление сохранённых натальных профилей."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.compatibility import crud as compatibility_crud
from astra.compatibility.models import NatalProfile
from astra.core.observability import Event, get_logger
from astra.telegram.button_texts import (
    CB_PEOPLE_CARD_PREFIX,
    CB_PEOPLE_DELETE_CANCEL_PREFIX,
    CB_PEOPLE_DELETE_CONFIRM_PREFIX,
    CB_PEOPLE_DELETE_PREFIX,
    CB_PEOPLE_EDIT_PREFIX,
    CB_PEOPLE_LIST,
    CB_PROFILE_PEOPLE,
)
from astra.telegram.keyboards import profile_menu_keyboard
from astra.telegram.keyboards_people import (
    CB_PEOPLE_GENDER_PREFIX,
    people_card_keyboard,
    people_delete_confirm_keyboard,
    people_gender_keyboard,
    people_list_keyboard,
)
from astra.telegram.profile_text import shorten_place_display
from astra.telegram.states import PeopleStates
from astra.telegram.utils import parse_birth_date, parse_birth_time
from astra.users import crud as users_crud
from astra.users.gender import GENDER_FEMALE, GENDER_MALE, gender_display_label
from astra.users.models import User

log = get_logger(__name__)

router = Router(name="people")

_EMPTY_LIST_TEXT = (
    "Пока нет сохранённых людей.\n"
    "Они появятся здесь после разбора — нажми «💕 Совместимость»."
)
_LIST_TITLE = "👥 <b>Мои люди</b>\nНажми на человека, чтобы открыть карточку."


def format_people_card(profile: NatalProfile) -> str:
    gender_line = gender_display_label(profile.gender) or "⚧ <i>пол не указан</i>"

    if profile.birth_time is not None:
        bt = profile.birth_time
        if bt.tzinfo is not None:
            bt = bt.astimezone(ZoneInfo(profile.timezone))
        time_line = f"🕐 {bt.strftime('%H:%M')}"
    else:
        time_line = "🕐 <i>время не указано</i>"

    place = (profile.birth_place or "").strip()
    place_line = f"📍 {shorten_place_display(place)}" if place else "📍 <i>место не указано</i>"

    return "\n".join(
        [
            f"👤 <b>{profile.label}</b>",
            "",
            gender_line,
            f"📅 {profile.birth_date.strftime('%d.%m.%Y')}",
            time_line,
            place_line,
        ],
    )


async def _get_user(session: AsyncSession, callback: CallbackQuery) -> User | None:
    if callback.from_user is None:
        return None
    return await users_crud.get_user_by_telegram_id(session, callback.from_user.id)


async def _load_owned_profile(
    session: AsyncSession,
    user: User,
    profile_id: UUID,
) -> NatalProfile | None:
    profile = await compatibility_crud.get_natal_profile_by_id(session, profile_id)
    if profile is None or profile.owner_user_id != user.id:
        return None
    return profile


async def _send_people_list(message: Message, session: AsyncSession, user: User) -> None:
    profiles = await compatibility_crud.list_natal_profiles(session, user.id)
    if not profiles:
        await message.answer(_EMPTY_LIST_TEXT, reply_markup=profile_menu_keyboard())
        return
    await message.answer(
        _LIST_TITLE,
        parse_mode="HTML",
        reply_markup=people_list_keyboard(profiles),
    )


async def _send_people_card(message: Message, profile: NatalProfile) -> None:
    await message.answer(
        format_people_card(profile),
        parse_mode="HTML",
        reply_markup=people_card_keyboard(str(profile.id)),
    )


@router.callback_query(F.data.in_({CB_PROFILE_PEOPLE, CB_PEOPLE_LIST}))
async def cb_people_list(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None:
        await callback.answer()
        return
    user = await _get_user(session, callback)
    if user is None:
        await callback.answer("Сначала: /start", show_alert=True)
        return
    await _send_people_list(callback.message, session, user)
    await callback.answer()


@router.callback_query(F.data.startswith(CB_PEOPLE_CARD_PREFIX))
async def cb_people_card(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer()
        return
    user = await _get_user(session, callback)
    if user is None:
        await callback.answer("Сначала: /start", show_alert=True)
        return
    profile = await _load_owned_profile(
        session,
        user,
        UUID(callback.data.removeprefix(CB_PEOPLE_CARD_PREFIX)),
    )
    if profile is None:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    await _send_people_card(callback.message, profile)
    await callback.answer()


@router.callback_query(F.data.startswith(CB_PEOPLE_EDIT_PREFIX))
async def cb_people_edit(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer()
        return
    field, _, raw_id = callback.data.removeprefix(CB_PEOPLE_EDIT_PREFIX).partition(":")
    user = await _get_user(session, callback)
    if user is None:
        await callback.answer("Сначала: /start", show_alert=True)
        return
    profile = await _load_owned_profile(session, user, UUID(raw_id))
    if profile is None:
        await callback.answer("Профиль не найден", show_alert=True)
        return

    if field == "gender":
        await callback.message.answer(
            f"Пол — <b>{profile.label}</b>:",
            parse_mode="HTML",
            reply_markup=people_gender_keyboard(str(profile.id)),
        )
        await callback.answer()
        return

    await state.update_data(people_profile_id=str(profile.id))
    if field == "name":
        await state.set_state(PeopleStates.edit_name)
        await callback.message.answer(f"Новое имя для <b>{profile.label}</b>:", parse_mode="HTML")
    elif field == "date":
        await state.set_state(PeopleStates.edit_birth_date)
        await callback.message.answer(
            f"Дата рождения — <b>{profile.label}</b> (ДД.ММ.ГГГГ):",
            parse_mode="HTML",
        )
    elif field == "time":
        await state.set_state(PeopleStates.edit_birth_time)
        await callback.message.answer(
            f"Время рождения — <b>{profile.label}</b> (ЧЧ:ММ, например 14:30):",
            parse_mode="HTML",
        )
    elif field == "place":
        from astra.telegram.handlers.places import start_people_birth_place_step

        await start_people_birth_place_step(callback.message, state, label=profile.label)
    else:
        await callback.answer("Неизвестное поле", show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith(CB_PEOPLE_GENDER_PREFIX))
async def cb_people_save_gender(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer()
        return
    value, _, raw_id = callback.data.removeprefix(CB_PEOPLE_GENDER_PREFIX).partition(":")
    user = await _get_user(session, callback)
    if user is None:
        await callback.answer("Сначала: /start", show_alert=True)
        return
    profile = await _load_owned_profile(session, user, UUID(raw_id))
    if profile is None:
        await callback.answer("Профиль не найден", show_alert=True)
        return

    gender = GENDER_MALE if value == "male" else GENDER_FEMALE
    await compatibility_crud.update_natal_profile(session, profile, gender=gender)
    log.info(Event.NATAL_PROFILE_UPDATED, profile_id=str(profile.id), field="gender")
    await _send_people_card(callback.message, profile)
    await callback.answer("Сохранено ✨")


async def _profile_from_state(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> NatalProfile | None:
    if message.from_user is None:
        return None
    user = await users_crud.get_user_by_telegram_id(session, message.from_user.id)
    if user is None:
        return None
    data = await state.get_data()
    raw_id = data.get("people_profile_id")
    if not raw_id:
        return None
    return await _load_owned_profile(session, user, UUID(str(raw_id)))


@router.message(PeopleStates.edit_name)
async def save_people_name(message: Message, state: FSMContext, session: AsyncSession) -> None:
    profile = await _profile_from_state(message, state, session)
    if profile is None:
        await state.clear()
        await message.answer("Что-то пошло не так. Открой профиль заново.")
        return
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Введи имя (минимум 2 символа).")
        return
    duplicate = await compatibility_crud.find_natal_profile_by_label(
        session,
        profile.owner_user_id,
        name,
    )
    if duplicate is not None and duplicate.id != profile.id:
        await message.answer(
            f"У тебя уже есть профиль с именем <b>{name}</b>. Выбери другое имя.",
            parse_mode="HTML",
        )
        return
    await compatibility_crud.update_natal_profile(session, profile, label=name)
    log.info(Event.NATAL_PROFILE_UPDATED, profile_id=str(profile.id), field="label")
    await state.clear()
    await _send_people_card(message, profile)


@router.message(PeopleStates.edit_birth_date)
async def save_people_birth_date(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    profile = await _profile_from_state(message, state, session)
    if profile is None:
        await state.clear()
        await message.answer("Что-то пошло не так. Открой профиль заново.")
        return
    parsed = parse_birth_date(message.text or "")
    if parsed is None:
        await message.answer("Не разобрал дату. Формат: ДД.ММ.ГГГГ (например 15.03.1990)")
        return

    update_fields: dict[str, object] = {"birth_date": parsed}
    if profile.birth_time is not None:
        update_fields["birth_time"] = profile.birth_time.replace(
            year=parsed.year,
            month=parsed.month,
            day=parsed.day,
        )
    await compatibility_crud.update_natal_profile(session, profile, **update_fields)
    log.info(Event.NATAL_PROFILE_UPDATED, profile_id=str(profile.id), field="birth_date")
    await state.clear()
    await _send_people_card(message, profile)


@router.message(PeopleStates.edit_birth_time)
async def save_people_birth_time(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    profile = await _profile_from_state(message, state, session)
    if profile is None:
        await state.clear()
        await message.answer("Что-то пошло не так. Открой профиль заново.")
        return
    parsed = parse_birth_time(message.text or "")
    if parsed is None:
        await message.answer("Не разобрал время. Формат: 14:30")
        return
    birth_dt = datetime.combine(profile.birth_date, parsed)
    await compatibility_crud.update_natal_profile(session, profile, birth_time=birth_dt)
    log.info(Event.NATAL_PROFILE_UPDATED, profile_id=str(profile.id), field="birth_time")
    await state.clear()
    await _send_people_card(message, profile)


async def complete_people_birth_place(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    *,
    place_display: str,
    place_id: UUID,
    timezone: str,
    actor_telegram_id: int,
) -> None:
    """Вызывается из places после выбора населённого пункта."""
    user = await users_crud.get_user_by_telegram_id(session, actor_telegram_id)
    data = await state.get_data()
    raw_id = data.get("people_profile_id")
    profile = (
        await _load_owned_profile(session, user, UUID(str(raw_id)))
        if user is not None and raw_id
        else None
    )
    if profile is None:
        await state.clear()
        await message.answer("Что-то пошло не так. Открой профиль заново.")
        return
    await compatibility_crud.update_natal_profile(
        session,
        profile,
        birth_place=place_display,
        birth_place_id=place_id,
        timezone=timezone,
    )
    log.info(Event.NATAL_PROFILE_UPDATED, profile_id=str(profile.id), field="birth_place")
    await state.clear()
    await _send_people_card(message, profile)


@router.callback_query(F.data.startswith(CB_PEOPLE_DELETE_CONFIRM_PREFIX))
async def cb_people_delete_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer()
        return
    user = await _get_user(session, callback)
    if user is None:
        await callback.answer("Сначала: /start", show_alert=True)
        return
    profile_id = UUID(callback.data.removeprefix(CB_PEOPLE_DELETE_CONFIRM_PREFIX))
    deleted = await compatibility_crud.delete_natal_profile(session, profile_id, user.id)
    if not deleted:
        await callback.answer("Не получилось удалить", show_alert=True)
        return
    log.info(Event.NATAL_PROFILE_DELETED, profile_id=str(profile_id))
    await callback.answer("Профиль удалён")
    await _send_people_list(callback.message, session, user)


@router.callback_query(F.data.startswith(CB_PEOPLE_DELETE_CANCEL_PREFIX))
async def cb_people_delete_cancel(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.answer("Оставила профиль как есть ✨")
    await callback.answer()


@router.callback_query(
    F.data.startswith(CB_PEOPLE_DELETE_PREFIX)
    & ~F.data.startswith(CB_PEOPLE_DELETE_CONFIRM_PREFIX)
    & ~F.data.startswith(CB_PEOPLE_DELETE_CANCEL_PREFIX),
)
async def cb_people_delete_prompt(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer()
        return
    user = await _get_user(session, callback)
    if user is None:
        await callback.answer("Сначала: /start", show_alert=True)
        return
    profile = await _load_owned_profile(
        session,
        user,
        UUID(callback.data.removeprefix(CB_PEOPLE_DELETE_PREFIX)),
    )
    if profile is None:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    await callback.message.answer(
        f"Удалить профиль <b>{profile.label}</b>?\n"
        "Готовые разборы с этим человеком останутся.",
        parse_mode="HTML",
        reply_markup=people_delete_confirm_keyboard(str(profile.id)),
    )
    await callback.answer()
