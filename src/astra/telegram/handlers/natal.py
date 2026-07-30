"""FSM разбора натальной карты: время рождения (если нет) → подтверждение → очередь."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)
from sqlalchemy.ext.asyncio import AsyncSession

from astra.compatibility import crud as compatibility_crud
from astra.compatibility.models import NatalProfile
from astra.core.observability import Event, get_logger
from astra.services.natal_report_service import (
    NatalRequestStatus,
    NatalSubject,
    create_natal_report_for_subject,
    create_natal_report_for_user,
    person_subtitle,
    request_natal_report,
)
from astra.telegram.button_texts import (
    BTN_GENDER_MALE,
    BTN_NATAL,
    BTN_TIME_UNKNOWN,
    CB_PROFILE_NATAL,
    GENDER_REPLY_BUTTONS,
)
from astra.telegram.keyboards import gender_keyboard, main_menu_keyboard, skip_keyboard
from astra.telegram.keyboards_people import person_pick_keyboard
from astra.telegram.progress import (
    NatalStage,
    current_progress_message_id,
    natal_job_key,
    notify_natal_stage,
)
from astra.telegram.states import NatalStates
from astra.astro.birth_time import wall_clock_at
from astra.telegram.utils import parse_birth_date, parse_birth_time
from astra.usage import ACTION_NATAL_REPORT, UsageKind, record_usage
from astra.users import crud as users_crud
from astra.users.gender import GENDER_FEMALE, GENDER_MALE

log = get_logger(__name__)

router = Router(name="natal")

CB_NATAL_CONFIRM = "natal:confirm"
CB_NATAL_CANCEL = "natal:cancel"
CB_NATAL_TIME_UNKNOWN = "natal:time_unknown"
CB_NATAL_SUBJECT_SELF = "natal:subject:self"
CB_NATAL_SUBJECT_NEW = "natal:subject:new"
CB_NATAL_SUBJECT_ALL = "natal:subject:all"
CB_NATAL_SUBJECT_PICK_PREFIX = "natal:subject:pick:"

_SUBJECT_PROFILE_KEY = "natal_subject_profile_id"
_NEW_PERSON_PREFIX = "natal_new_"
_SKIP_TIME_TEXT = "⏭ Пропустить"
_NATAL_PICKER_LIMIT = 6

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
            [InlineKeyboardButton(text=BTN_TIME_UNKNOWN, callback_data=CB_NATAL_TIME_UNKNOWN)],
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


async def _show_confirm_view(
    message: Message,
    state: FSMContext,
    *,
    display_name: str,
    birth_date: date,
    birth_time: datetime | None,
    birth_place: str | None,
) -> None:
    subtitle = person_subtitle(birth_date, birth_time, birth_place)
    lines = [
        "🌌 <b>Разбор натальной карты</b>",
        "",
        f"<b>{display_name}</b>",
        subtitle,
        "",
        "В разборе: колесо карты, ядро личности, сильные стороны,",
        "сферы жизни, кармический вектор и практикум — PDF на ~14 страниц.",
    ]
    if birth_time is None:
        lines += ["", _NO_TIME_WARNING]
    await state.set_state(NatalStates.confirm)
    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=_confirm_keyboard(),
    )


async def _show_confirm(message: Message, state: FSMContext, user) -> None:  # noqa: ANN001
    profile = user.profile
    await _show_confirm_view(
        message,
        state,
        display_name=profile.display_name,
        birth_date=profile.birth_date,
        birth_time=profile.birth_time,
        birth_place=profile.birth_place,
    )


async def _show_confirm_profile(
    message: Message,
    state: FSMContext,
    profile: NatalProfile,
) -> None:
    await _show_confirm_view(
        message,
        state,
        display_name=profile.label,
        birth_date=profile.birth_date,
        birth_time=profile.birth_time,
        birth_place=profile.birth_place,
    )


def _subject_keyboard(
    profiles: list[NatalProfile],
    *,
    show_all: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="🙋 Разбор для меня", callback_data=CB_NATAL_SUBJECT_SELF)],
        [InlineKeyboardButton(text="➕ Новый человек", callback_data=CB_NATAL_SUBJECT_NEW)],
    ]
    # Сворачиваем, только если за кнопкой прячется больше одного человека:
    # ряд «Показать всех» ради одной строки не экономит место.
    collapsed = not show_all and len(profiles) > _NATAL_PICKER_LIMIT + 1
    visible = profiles[:_NATAL_PICKER_LIMIT] if collapsed else profiles
    picker = person_pick_keyboard(visible, callback_prefix=CB_NATAL_SUBJECT_PICK_PREFIX)
    rows.extend(picker.inline_keyboard)
    if collapsed:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🔛 Показать всех ({len(profiles)})",
                    callback_data=CB_NATAL_SUBJECT_ALL,
                ),
            ],
        )
    rows.append([InlineKeyboardButton(text="Отмена", callback_data=CB_NATAL_CANCEL)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _load_subject_profile(
    session: AsyncSession,
    user,  # noqa: ANN001
    state: FSMContext,
) -> NatalProfile | None:
    data = await state.get_data()
    raw_id = data.get(_SUBJECT_PROFILE_KEY)
    if not raw_id:
        return None
    profile = await compatibility_crud.get_natal_profile_by_id(session, UUID(str(raw_id)))
    if profile is None or profile.owner_user_id != user.id:
        return None
    return profile


async def _begin_self_flow(message: Message, state: FSMContext, user) -> None:  # noqa: ANN001
    """Разбор для самого пользователя: спросить время, если его нет, иначе подтверждение."""
    await state.update_data(**{_SUBJECT_PROFILE_KEY: None})
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


@router.message(F.text == BTN_NATAL)
async def start_natal(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user = await _require_user(message, session)
    if user is None:
        return
    await state.clear()
    profiles = await compatibility_crud.list_natal_profiles(session, user.id)
    await message.answer(
        "🌌 <b>Разбор натальной карты</b>\n\nДля кого построить разбор?",
        parse_mode="HTML",
        reply_markup=_subject_keyboard(profiles),
    )


@router.callback_query(F.data == CB_PROFILE_NATAL)
async def cb_natal_from_profile(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Вход в разбор из портрета «Обо мне».

    Пользователя берём по `callback.from_user`: у сообщения с кнопкой автор —
    бот, и `_require_user` искал бы в базе его.
    """
    await callback.answer()
    if callback.message is None or callback.from_user is None:
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None or not user.onboarding_completed or user.profile is None:
        await callback.message.answer("Сначала пройди регистрацию: /start")
        return
    await state.clear()
    profiles = await compatibility_crud.list_natal_profiles(session, user.id)
    await callback.message.answer(
        "🌌 <b>Разбор натальной карты</b>\n\nДля кого построить разбор?",
        parse_mode="HTML",
        reply_markup=_subject_keyboard(profiles),
    )


@router.callback_query(F.data == CB_NATAL_SUBJECT_ALL)
async def cb_natal_subject_all(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None or callback.from_user is None:
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        return
    profiles = await compatibility_crud.list_natal_profiles(session, user.id)
    await callback.message.edit_reply_markup(
        reply_markup=_subject_keyboard(profiles, show_all=True),
    )


@router.callback_query(F.data == CB_NATAL_SUBJECT_SELF)
async def cb_natal_subject_self(
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
    await _begin_self_flow(callback.message, state, user)


@router.callback_query(F.data.startswith(CB_NATAL_SUBJECT_PICK_PREFIX))
async def cb_natal_subject_pick(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None or callback.from_user is None or callback.data is None:
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        return
    profile = await compatibility_crud.get_natal_profile_by_id(
        session,
        UUID(callback.data.removeprefix(CB_NATAL_SUBJECT_PICK_PREFIX)),
    )
    if profile is None or profile.owner_user_id != user.id:
        await callback.message.answer("Профиль не найден.")
        return

    await state.update_data(**{_SUBJECT_PROFILE_KEY: str(profile.id)})
    log.info(Event.NATAL_PROFILE_PICKED, profile_id=str(profile.id))
    if profile.birth_time is None:
        await state.set_state(NatalStates.collect_birth_time)
        await callback.message.answer(
            f"🌌 Разбор для <b>{profile.label}</b>.\n\n"
            "Для асцендента и домов нужно время рождения.\n"
            "Напиши его в формате <b>14:30</b> — или нажми «Не знаю».",
            parse_mode="HTML",
            reply_markup=_time_keyboard(),
        )
        return
    await _show_confirm_profile(callback.message, state, profile)


@router.callback_query(F.data == CB_NATAL_SUBJECT_NEW)
async def cb_natal_subject_new(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.update_data(**{_SUBJECT_PROFILE_KEY: None})
    await state.set_state(NatalStates.new_name)
    await callback.message.answer(
        "🌌 <b>Разбор для нового человека</b>\n\nКак его/её зовут?",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(NatalStates.new_name)
async def collect_new_name(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if await _require_user(message, session) is None:
        return
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Введи имя (минимум 2 символа).")
        return
    await state.update_data(**{f"{_NEW_PERSON_PREFIX}name": name})
    await state.set_state(NatalStates.new_gender)
    await message.answer(f"Пол — <b>{name}</b>:", parse_mode="HTML", reply_markup=gender_keyboard())


@router.message(NatalStates.new_gender, F.text.in_(GENDER_REPLY_BUTTONS))
async def collect_new_gender(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if await _require_user(message, session) is None:
        return
    gender = GENDER_MALE if message.text == BTN_GENDER_MALE else GENDER_FEMALE
    await state.update_data(**{f"{_NEW_PERSON_PREFIX}gender": gender})
    await state.set_state(NatalStates.new_birth_date)
    await message.answer(
        "Дата рождения (ДД.ММ.ГГГГ):",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(NatalStates.new_birth_date)
async def collect_new_birth_date(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if await _require_user(message, session) is None:
        return
    parsed = parse_birth_date(message.text or "")
    if parsed is None:
        await message.answer("Не разобрала дату. Формат: ДД.ММ.ГГГГ")
        return
    await state.update_data(**{f"{_NEW_PERSON_PREFIX}birth_date": parsed.isoformat()})
    await state.set_state(NatalStates.new_birth_time)
    await message.answer(
        "Время рождения (ЧЧ:ММ).\n"
        "Для асцендента и домов оно важно — но если не знаешь, нажми «⏭ Пропустить».",
        reply_markup=skip_keyboard(),
    )


@router.message(NatalStates.new_birth_time, F.text == _SKIP_TIME_TEXT)
async def skip_new_birth_time(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if await _require_user(message, session) is None:
        return
    await state.update_data(**{f"{_NEW_PERSON_PREFIX}birth_time": None})
    from astra.telegram.handlers.places import start_natal_new_birth_place_step

    await start_natal_new_birth_place_step(message, state)


@router.message(NatalStates.new_birth_time)
async def collect_new_birth_time(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if await _require_user(message, session) is None:
        return
    parsed = parse_birth_time(message.text or "")
    if parsed is None:
        await message.answer("Не разобрала время. Формат: 14:30 или «⏭ Пропустить».")
        return
    data = await state.get_data()
    birth_date = date.fromisoformat(str(data[f"{_NEW_PERSON_PREFIX}birth_date"]))
    birth_dt = wall_clock_at(birth_date, parsed)
    await state.update_data(**{f"{_NEW_PERSON_PREFIX}birth_time": birth_dt.isoformat()})
    from astra.telegram.handlers.places import start_natal_new_birth_place_step

    await start_natal_new_birth_place_step(message, state)


async def complete_natal_new_birth_place(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    *,
    place_display: str,
    place_id: UUID,
    timezone: str,
    actor_telegram_id: int,
) -> None:
    """Данные нового человека собраны: сохранить профиль и показать подтверждение."""
    user = await users_crud.get_user_by_telegram_id(session, actor_telegram_id)
    if user is None:
        await state.clear()
        await message.answer("Что-то пошло не так. Нажми /start")
        return
    data = await state.get_data()
    name = str(data.get(f"{_NEW_PERSON_PREFIX}name") or "").strip()
    if len(name) < 2:
        await state.clear()
        await message.answer("Что-то пошло не так. Начни разбор заново.")
        return
    birth_date = date.fromisoformat(str(data[f"{_NEW_PERSON_PREFIX}birth_date"]))
    birth_time_raw = data.get(f"{_NEW_PERSON_PREFIX}birth_time")
    birth_time = datetime.fromisoformat(str(birth_time_raw)) if birth_time_raw else None

    profile = await compatibility_crud.upsert_natal_profile(
        session,
        owner_user_id=user.id,
        label=name,
        gender=data.get(f"{_NEW_PERSON_PREFIX}gender"),
        birth_date=birth_date,
        birth_time=birth_time,
        birth_place=place_display,
        birth_place_id=place_id,
        timezone=timezone,
    )
    log.info(Event.NATAL_PROFILE_UPDATED, profile_id=str(profile.id), field="new_person")

    for key in ("name", "gender", "birth_date", "birth_time"):
        data.pop(f"{_NEW_PERSON_PREFIX}{key}", None)
    await state.set_data(data)
    await state.update_data(**{_SUBJECT_PROFILE_KEY: str(profile.id)})
    await _show_confirm_profile(message, state, profile)


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

    profile = await _load_subject_profile(session, user, state)
    if profile is not None:
        birth_dt = wall_clock_at(profile.birth_date, parsed)
        await compatibility_crud.update_natal_profile(session, profile, birth_time=birth_dt)
        await session.commit()
        await _show_confirm_profile(message, state, profile)
        return

    birth_dt = wall_clock_at(user.profile.birth_date, parsed)
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
    profile = await _load_subject_profile(session, user, state)
    if profile is not None:
        await _show_confirm_profile(callback.message, state, profile)
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
        profile = await _load_subject_profile(session, user, state)
        if profile is not None:
            subject = NatalSubject(
                name=profile.label,
                gender=profile.gender,
                birth_date=profile.birth_date,
                birth_time=profile.birth_time,
                birth_place=profile.birth_place,
                birth_place_id=profile.birth_place_id,
                timezone=profile.timezone,
            )
            report = await create_natal_report_for_subject(session, user, subject)
        else:
            report = await create_natal_report_for_user(session, user)
        await record_usage(
            session,
            user,
            action=ACTION_NATAL_REPORT,
            kind=UsageKind.NATAL,
            is_paid=False,
        )
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
