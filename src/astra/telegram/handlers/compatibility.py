"""FSM совместимости: контекст → режим → данные → PDF."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from astra.core.observability import Event, get_logger

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)
from sqlalchemy.ext.asyncio import AsyncSession

from astra.compatibility.enums import (
    COMPATIBILITY_IN_FLIGHT_STATUSES,
    PairMode,
    RelationshipContext,
    ReportStatus,
)
from astra.compatibility.models import CompatibilityReport
from astra.compatibility import crud as compatibility_crud
from astra.services.compatibility_service import (
    CompatibilityRequestStatus,
    FsmPersonData,
    compatibility_context_emoji,
    create_report_from_fsm,
    delete_compatibility_report_for_user,
    request_compatibility_report,
)
from astra.telegram.progress import (
    CompatibilityStage,
    current_progress_message_id,
    compatibility_job_key,
    notify_compatibility_stage,
)
from astra.telegram.button_texts import (
    BTN_COMPATIBILITY,
    BTN_GENDER_FEMALE,
    BTN_GENDER_MALE,
    CB_COMPAT_CANCEL,
    CB_COMPAT_CONFIRM,
    CB_COMPAT_CONTEXT_PREFIX,
    CB_COMPAT_REPORT_PREFIX,
    CB_COMPAT_REPORT_PDF_PREFIX,
    CB_COMPAT_REPORTS_LIST,
    CB_COMPAT_DELETE_PREFIX,
    CB_COMPAT_DELETE_CONFIRM_PREFIX,
    CB_COMPAT_DELETE_CANCEL_PREFIX,
    CB_COMPAT_NEW_PERSON,
    CB_COMPAT_PEOPLE_ALL,
    CB_COMPAT_SELF_FIRST,
    CB_PERSON_PICK_PREFIX,
    CB_PROFILE_REPORTS,
    GENDER_REPLY_BUTTONS,
)
from astra.telegram.handlers.places import (
    handle_place_query,
    start_compatibility_birth_place_step,
)
from astra.telegram.keyboards import (
    compatibility_confirm_keyboard,
    compatibility_context_keyboard,
    compatibility_delete_confirm_keyboard,
    compatibility_report_card_keyboard,
    compatibility_reports_keyboard,
    gender_keyboard,
    main_menu_keyboard,
    profile_menu_keyboard,
    skip_keyboard,
)
from astra.telegram.keyboards_people import person_pick_keyboard
from astra.telegram.states import CompatibilityStates
from astra.telegram.utils import parse_birth_date, parse_birth_time
from astra.users import crud as users_crud
from astra.users.gender import GENDER_FEMALE, GENDER_MALE

log = get_logger(__name__)

router = Router(name="compatibility")

SKIP_TIME_TEXT = "⏭ Пропустить"
COLLECTING_PERSON_A = "person_a"
COLLECTING_PERSON_B = "person_b"


def _person_label(collecting: str) -> str:
    return "первого человека" if collecting == COLLECTING_PERSON_A else "партнёра"


async def _require_user(message: Message, session: AsyncSession):
    if message.from_user is None:
        return None
    user = await users_crud.get_user_by_telegram_id(session, message.from_user.id)
    if user is None or not user.onboarding_completed or user.profile is None:
        await message.answer("Сначала пройди регистрацию: /start")
        return None
    return user


@router.message(F.text == BTN_COMPATIBILITY)
async def start_compatibility(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user = await _require_user(message, session)
    if user is None:
        return
    await state.clear()
    await state.set_state(CompatibilityStates.choose_context)
    await message.answer(
        "💕 <b>Совместимость</b>\n\nВыбери контекст разбора:",
        parse_mode="HTML",
        reply_markup=compatibility_context_keyboard(),
    )


@router.callback_query(F.data.startswith(CB_COMPAT_CONTEXT_PREFIX))
async def cb_choose_context(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.message is None or callback.data is None or callback.from_user is None:
        await callback.answer()
        return
    value = callback.data.removeprefix(CB_COMPAT_CONTEXT_PREFIX)
    if value not in {c.value for c in RelationshipContext}:
        await callback.answer("Неизвестный контекст", show_alert=True)
        return

    # По умолчанию — «другая пара»; выбор «🙋 Я» первым переключит на «мою совместимость».
    await state.update_data(
        relationship_context=value,
        pair_mode=PairMode.TWO_PEOPLE.value,
        collecting=COLLECTING_PERSON_A,
    )
    await _send_person_step(
        callback.message,
        state,
        session,
        actor_telegram_id=callback.from_user.id,
        heading="👥 Кто <b>первый человек</b>?",
        name_prompt="Как зовут <b>первого человека</b>?",
        with_self=True,
    )
    await callback.answer()


_PROFILE_PICKER_LIMIT = 6
_NAME_PROMPT_KEY = "person_step_name_prompt"


def _compat_person_keyboard(
    profiles: list,
    *,
    show_all: bool = False,
    with_self: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if with_self:
        rows.append([InlineKeyboardButton(text="🙋 Я", callback_data=CB_COMPAT_SELF_FIRST)])
    rows.append(
        [InlineKeyboardButton(text="➕ Новый человек", callback_data=CB_COMPAT_NEW_PERSON)],
    )
    visible = profiles if show_all else profiles[:_PROFILE_PICKER_LIMIT]
    picker = person_pick_keyboard(visible)
    rows.extend(picker.inline_keyboard)
    if not show_all and len(profiles) > _PROFILE_PICKER_LIMIT:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🔛 Показать всех ({len(profiles)})",
                    callback_data=CB_COMPAT_PEOPLE_ALL,
                ),
            ],
        )
    rows.append([InlineKeyboardButton(text="Отмена", callback_data=CB_COMPAT_CANCEL)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _selectable_profiles(session: AsyncSession, state: FSMContext, user_id: UUID) -> list:
    profiles = await compatibility_crud.list_natal_profiles(session, user_id)
    data = await state.get_data()
    picked_a = data.get("person_a_picked_profile_id")
    if picked_a:
        profiles = [p for p in profiles if str(p.id) != str(picked_a)]
    return profiles


async def _send_person_step(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    *,
    actor_telegram_id: int,
    heading: str,
    name_prompt: str,
    with_self: bool = False,
) -> None:
    """Единый экран выбора человека: сохранённые + «Новый человек» (+ «Я»), иначе сразу ввод имени."""
    await state.set_state(CompatibilityStates.collect_name)
    await state.update_data(**{_NAME_PROMPT_KEY: name_prompt})
    user = await users_crud.get_user_by_telegram_id(session, actor_telegram_id)
    profiles = await _selectable_profiles(session, state, user.id) if user else []
    # На первом участнике экран показываем всегда — там есть «Я», даже без сохранённых.
    if not profiles and not with_self:
        await message.answer(name_prompt, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
        return
    await message.answer(
        heading,
        parse_mode="HTML",
        reply_markup=_compat_person_keyboard(profiles, with_self=with_self),
    )


async def _prompt_next_person_step(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    actor_telegram_id: int,
) -> None:
    """Спросить первое недостающее поле текущего человека или завершить сбор."""
    data = await state.get_data()
    collecting = data.get("collecting", COLLECTING_PERSON_B)
    label = _person_label(collecting)
    if f"{collecting}_gender" not in data:
        await state.set_state(CompatibilityStates.collect_gender)
        await message.answer(f"Пол {label}:", reply_markup=gender_keyboard())
        return
    if f"{collecting}_birth_date" not in data:
        await state.set_state(CompatibilityStates.collect_birth_date)
        await message.answer(
            f"Дата рождения {label} (ДД.ММ.ГГГГ):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return
    if f"{collecting}_birth_time" not in data:
        await state.set_state(CompatibilityStates.collect_birth_time)
        await message.answer(
            f"Время рождения {label} (ЧЧ:ММ).\n"
            "Если не знаешь — нажми «⏭ Пропустить».",
            reply_markup=skip_keyboard(),
        )
        return
    if f"{collecting}_birth_place" not in data:
        await start_compatibility_birth_place_step(message, state, collecting=collecting)
        return
    await _finish_person_collection(message, state, session, actor_telegram_id)


async def _finish_person_collection(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    actor_telegram_id: int,
) -> None:
    """Данные человека собраны: перейти ко второму человеку или к подтверждению."""
    data = await state.get_data()
    collecting = data.get("collecting", COLLECTING_PERSON_B)
    pair_mode = data.get("pair_mode", PairMode.ME_PARTNER)
    if pair_mode == PairMode.TWO_PEOPLE and collecting == COLLECTING_PERSON_A:
        await state.update_data(collecting=COLLECTING_PERSON_B)
        await _send_person_step(
            message,
            state,
            session,
            actor_telegram_id=actor_telegram_id,
            heading="👥 Кто <b>второй человек</b>?",
            name_prompt="Данные <b>второго человека</b>.\n\nКак его/её зовут?",
        )
        return
    await _show_confirm(message, state)


@router.callback_query(
    StateFilter(CompatibilityStates.collect_name),
    F.data == CB_COMPAT_SELF_FIRST,
)
async def cb_compat_self_first(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Первый участник — сам пользователь: это «моя совместимость», дальше только партнёр."""
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    await state.update_data(
        pair_mode=PairMode.ME_PARTNER.value,
        collecting=COLLECTING_PERSON_B,
    )
    await _send_person_step(
        callback.message,
        state,
        session,
        actor_telegram_id=callback.from_user.id,
        heading="Данные о <b>тебе</b> возьму из профиля.\n\n👥 Кто <b>партнёр</b>?",
        name_prompt=(
            "Данные о <b>тебе</b> возьму из профиля.\n\n"
            "Как зовут <b>партнёра</b>?"
        ),
    )
    await callback.answer()


@router.callback_query(
    StateFilter(CompatibilityStates.collect_name),
    F.data == CB_COMPAT_NEW_PERSON,
)
async def cb_compat_new_person(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return
    data = await state.get_data()
    prompt = str(data.get(_NAME_PROMPT_KEY) or "Как зовут человека?")
    await callback.message.answer(prompt, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    await callback.answer()


@router.callback_query(
    StateFilter(CompatibilityStates.collect_name),
    F.data == CB_COMPAT_PEOPLE_ALL,
)
async def cb_compat_people_all(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await callback.answer()
        return
    profiles = await _selectable_profiles(session, state, user.id)
    data = await state.get_data()
    # «Я» доступен только на первом участнике — сохраняем кнопку при развороте списка.
    with_self = data.get("collecting", COLLECTING_PERSON_B) == COLLECTING_PERSON_A
    await callback.message.edit_reply_markup(
        reply_markup=_compat_person_keyboard(profiles, show_all=True, with_self=with_self),
    )
    await callback.answer()


@router.callback_query(
    StateFilter(CompatibilityStates.collect_name),
    F.data.startswith(CB_PERSON_PICK_PREFIX),
)
async def cb_pick_person_profile(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.message is None or callback.data is None or callback.from_user is None:
        await callback.answer()
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await callback.answer("Сначала: /start", show_alert=True)
        return
    profile = await compatibility_crud.get_natal_profile_by_id(
        session,
        UUID(callback.data.removeprefix(CB_PERSON_PICK_PREFIX)),
    )
    if profile is None or profile.owner_user_id != user.id:
        await callback.answer("Профиль не найден", show_alert=True)
        return

    data = await state.get_data()
    collecting = data.get("collecting", COLLECTING_PERSON_B)
    updates: dict[str, object] = {
        f"{collecting}_name": profile.label,
        f"{collecting}_birth_date": profile.birth_date.isoformat(),
        f"{collecting}_birth_place": profile.birth_place,
        f"{collecting}_birth_place_id": (
            str(profile.birth_place_id) if profile.birth_place_id else None
        ),
        f"{collecting}_timezone": profile.timezone,
    }
    if profile.gender:
        updates[f"{collecting}_gender"] = profile.gender
    if profile.birth_time is not None:
        birth_time = profile.birth_time
        if birth_time.tzinfo is not None:
            from zoneinfo import ZoneInfo

            birth_time = birth_time.astimezone(ZoneInfo(profile.timezone)).replace(tzinfo=None)
        updates[f"{collecting}_birth_time"] = birth_time.isoformat()
    if collecting == COLLECTING_PERSON_A:
        updates["person_a_picked_profile_id"] = str(profile.id)
    await state.update_data(**updates)
    log.info(Event.NATAL_PROFILE_PICKED, profile_id=str(profile.id))

    await callback.message.answer(
        f"Беру данные: <b>{profile.label}</b> ✨",
        parse_mode="HTML",
    )
    await _prompt_next_person_step(callback.message, state, session, callback.from_user.id)
    await callback.answer()


@router.message(CompatibilityStates.collect_name)
async def collect_name(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if await _require_user(message, session) is None:
        return
    if message.from_user is None:
        return
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Введи имя (минимум 2 символа).")
        return
    data = await state.get_data()
    collecting = data.get("collecting", COLLECTING_PERSON_B)
    await state.update_data(**{f"{collecting}_name": name})
    await _prompt_next_person_step(message, state, session, message.from_user.id)


@router.message(CompatibilityStates.collect_gender, F.text.in_(GENDER_REPLY_BUTTONS))
async def collect_gender(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if await _require_user(message, session) is None:
        return
    if message.from_user is None:
        return
    data = await state.get_data()
    collecting = data.get("collecting", COLLECTING_PERSON_B)
    gender = GENDER_MALE if message.text == BTN_GENDER_MALE else GENDER_FEMALE
    await state.update_data(**{f"{collecting}_gender": gender})
    await _prompt_next_person_step(message, state, session, message.from_user.id)


@router.message(CompatibilityStates.collect_birth_date)
async def collect_birth_date(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if await _require_user(message, session) is None:
        return
    if message.from_user is None:
        return
    parsed = parse_birth_date(message.text or "")
    if parsed is None:
        await message.answer("Не разобрал дату. Формат: ДД.ММ.ГГГГ")
        return
    data = await state.get_data()
    collecting = data.get("collecting", COLLECTING_PERSON_B)
    await state.update_data(**{f"{collecting}_birth_date": parsed.isoformat()})
    await _prompt_next_person_step(message, state, session, message.from_user.id)


@router.message(CompatibilityStates.collect_birth_time, F.text == SKIP_TIME_TEXT)
async def skip_birth_time(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if await _require_user(message, session) is None:
        return
    if message.from_user is None:
        return
    data = await state.get_data()
    collecting = data.get("collecting", COLLECTING_PERSON_B)
    await state.update_data(**{f"{collecting}_birth_time": None})
    await _prompt_next_person_step(message, state, session, message.from_user.id)


@router.message(CompatibilityStates.collect_birth_time)
async def collect_birth_time(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if await _require_user(message, session) is None:
        return
    if message.from_user is None:
        return
    parsed = parse_birth_time(message.text or "")
    if parsed is None:
        await message.answer("Не разобрал время. Формат: 14:30 или «⏭ Пропустить».")
        return
    data = await state.get_data()
    collecting = data.get("collecting", COLLECTING_PERSON_B)
    birth_date = date.fromisoformat(str(data[f"{collecting}_birth_date"]))
    birth_dt = datetime.combine(birth_date, parsed)
    await state.update_data(**{f"{collecting}_birth_time": birth_dt.isoformat()})
    await _prompt_next_person_step(message, state, session, message.from_user.id)


@router.message(StateFilter(CompatibilityStates.birth_place_query), F.text)
async def compatibility_place_search(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await handle_place_query(message, state, session, context_key="compatibility")


def _fsm_person_from_state(data: dict, prefix: str) -> FsmPersonData:
    birth_time_raw = data.get(f"{prefix}_birth_time")
    birth_time = datetime.fromisoformat(birth_time_raw) if birth_time_raw else None
    place_id_raw = data.get(f"{prefix}_birth_place_id")
    return FsmPersonData(
        name=str(data[f"{prefix}_name"]),
        gender=data.get(f"{prefix}_gender"),
        birth_date=date.fromisoformat(str(data[f"{prefix}_birth_date"])),
        birth_time=birth_time,
        birth_place=str(data.get(f"{prefix}_birth_place") or ""),
        birth_place_id=UUID(str(place_id_raw)) if place_id_raw else None,
        timezone=str(data.get(f"{prefix}_timezone") or "Europe/Moscow"),
    )


async def _show_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    pair_mode = data.get("pair_mode", PairMode.ME_PARTNER)
    if pair_mode == PairMode.ME_PARTNER:
        lines = [
            f"<b>Партнёр:</b> {data['person_b_name']}, "
            f"{date.fromisoformat(data['person_b_birth_date']).strftime('%d.%m.%Y')}, "
            f"{data.get('person_b_birth_place', '')}",
        ]
    else:
        lines = [
            f"<b>{data['person_a_name']}</b> — "
            f"{date.fromisoformat(data['person_a_birth_date']).strftime('%d.%m.%Y')}, "
            f"{data.get('person_a_birth_place', '')}",
            f"<b>{data['person_b_name']}</b> — "
            f"{date.fromisoformat(data['person_b_birth_date']).strftime('%d.%m.%Y')}, "
            f"{data.get('person_b_birth_place', '')}",
        ]
    await state.set_state(CompatibilityStates.confirm)
    await message.answer(
        "Проверь данные:\n\n" + "\n".join(lines) + "\n\nСоздать PDF-разбор?",
        parse_mode="HTML",
        reply_markup=compatibility_confirm_keyboard(),
    )


async def complete_person_birth_place(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    *,
    place_display: str,
    place_id: UUID,
    timezone: str,
    actor_telegram_id: int,
) -> None:
    data = await state.get_data()
    collecting = data.get("collecting", COLLECTING_PERSON_B)
    await state.update_data(
        **{
            f"{collecting}_birth_place": place_display,
            f"{collecting}_birth_place_id": str(place_id),
            f"{collecting}_timezone": timezone,
        },
    )
    await _finish_person_collection(message, state, session, actor_telegram_id)


@router.callback_query(F.data == CB_COMPAT_CANCEL)
async def cb_compat_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Отменено.", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == CB_COMPAT_CONFIRM)
async def cb_compat_confirm(
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

    data = await state.get_data()
    try:
        context = RelationshipContext(str(data["relationship_context"]))
        pair_mode = PairMode(str(data["pair_mode"]))
        person_b = _fsm_person_from_state(data, COLLECTING_PERSON_B)
        person_a = (
            _fsm_person_from_state(data, COLLECTING_PERSON_A)
            if pair_mode == PairMode.TWO_PEOPLE
            else None
        )
        report = await create_report_from_fsm(
            session,
            user,
            relationship_context=context,
            pair_mode=pair_mode,
            person_a=person_a,
            person_b=person_b,
        )
        await session.commit()
        outcome = await request_compatibility_report(session, report.id)
    except Exception:
        log.exception(Event.COMPATIBILITY_REPORT_CREATE_FAILED)
        await callback.message.answer(
            "Не получилось создать разбор. Попробуй позже.",
            reply_markup=main_menu_keyboard(),
        )
        await state.clear()
        await callback.answer()
        return

    await state.clear()
    if outcome.status == CompatibilityRequestStatus.FAILED:
        await callback.message.answer(
            "Не получилось запустить генерацию. Проверь DeepSeek в настройках.",
            reply_markup=main_menu_keyboard(),
        )
    elif outcome.status == CompatibilityRequestStatus.IN_PROGRESS:
        job_key = compatibility_job_key(report.id)
        if await current_progress_message_id(user.id, job_key) is None:
            await notify_compatibility_stage(
                callback.message.chat.id,
                user.id,
                report.id,
                CompatibilityStage.STARTED,
            )
        await callback.message.answer(
            "Разбор уже готовится — пришлю сюда, как только будет готов ✨",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await notify_compatibility_stage(
            callback.message.chat.id,
            user.id,
            report.id,
            CompatibilityStage.STARTED,
        )
        await callback.message.answer(
            "Приняла вашу пару в работу — скоро пришлю разбор ✨",
            reply_markup=main_menu_keyboard(),
        )
    await callback.answer()


def _report_status_label(report: CompatibilityReport) -> str:
    if report.pdf_path:
        return "✅ PDF готов"
    status = ReportStatus(report.status)
    if status == ReportStatus.FAILED:
        return "❌ Не удалось сгенерировать"
    if status in COMPATIBILITY_IN_FLIGHT_STATUSES or status == ReportStatus.PENDING:
        return "⏳ Готовится"
    return "⏳ Готовится"


def _format_report_card_text(report: CompatibilityReport) -> str:
    created = report.created_at.strftime("%d.%m.%Y %H:%M") if report.created_at else "—"
    return (
        f"{compatibility_context_emoji(report.relationship_context)} <b>{report.title}</b>\n\n"
        f"Статус: {_report_status_label(report)}\n"
        f"Создан: {created}"
    )


def _report_list_buttons(reports: list[CompatibilityReport]) -> list[tuple[str, str]]:
    buttons: list[tuple[str, str]] = []
    for report in reports:
        status_icon = "✅" if report.pdf_path else "⏳"
        created = report.created_at.strftime("%d.%m") if report.created_at else ""
        label = f"{status_icon} {report.title} ({created})"
        buttons.append((label, str(report.id)))
    return buttons


def _reports_list_text() -> str:
    return "📚 <b>Мои разборы</b>\nНажми на разбор, чтобы открыть карточку."


async def _send_reports_list(message: Message, reports: list[CompatibilityReport]) -> None:
    await message.answer(
        _reports_list_text(),
        parse_mode="HTML",
        reply_markup=compatibility_reports_keyboard(_report_list_buttons(reports)),
    )


@router.callback_query(F.data == CB_PROFILE_REPORTS)
async def cb_profile_reports(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await callback.answer("Сначала: /start", show_alert=True)
        return

    reports = await compatibility_crud.list_compatibility_reports(session, user.id, limit=15)
    if not reports:
        await callback.message.answer(
            "Пока нет сохранённых разборов.\nНажми «💕 Совместимость», чтобы создать первый.",
            reply_markup=profile_menu_keyboard(),
        )
        await callback.answer()
        return

    buttons = _report_list_buttons(reports)
    await callback.message.answer(
        _reports_list_text(),
        parse_mode="HTML",
        reply_markup=compatibility_reports_keyboard(buttons),
    )
    await callback.answer()


@router.callback_query(F.data == "profile:back")
async def cb_profile_back(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None or user.profile is None:
        await callback.answer()
        return
    from astra.telegram.profile_text import format_profile_card

    await callback.message.answer(
        format_profile_card(user, user.profile),
        parse_mode="HTML",
        reply_markup=profile_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith(CB_COMPAT_REPORT_PREFIX))
async def cb_open_report_card(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.from_user is None or callback.data is None:
        await callback.answer()
        return
    report_id = UUID(callback.data.removeprefix(CB_COMPAT_REPORT_PREFIX))
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await callback.answer()
        return

    report = await compatibility_crud.get_compatibility_report(session, report_id)
    if report is None or report.owner_user_id != user.id:
        await callback.answer("Разбор не найден", show_alert=True)
        return

    await callback.message.answer(
        _format_report_card_text(report),
        parse_mode="HTML",
        reply_markup=compatibility_report_card_keyboard(str(report.id)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith(CB_COMPAT_REPORT_PDF_PREFIX))
async def cb_send_report_pdf(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.from_user is None or callback.data is None:
        await callback.answer()
        return
    report_id = UUID(callback.data.removeprefix(CB_COMPAT_REPORT_PDF_PREFIX))
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await callback.answer()
        return

    from astra.services.compatibility_service import deliver_compatibility_report

    report = await compatibility_crud.get_compatibility_report(session, report_id)
    if report is None or report.owner_user_id != user.id:
        await callback.answer("Разбор не найден", show_alert=True)
        return

    if report.pdf_path:
        sent = await deliver_compatibility_report(session, report_id, resend=True)
        await session.commit()
        if sent:
            await callback.answer("PDF отправлен ✨")
            return

    await callback.answer("PDF ещё не готов", show_alert=True)


@router.callback_query(F.data == CB_COMPAT_REPORTS_LIST)
async def cb_back_to_reports_list(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await callback.answer()
        return

    reports = await compatibility_crud.list_compatibility_reports(session, user.id, limit=15)
    if not reports:
        await callback.message.answer(
            "Пока нет сохранённых разборов.",
            reply_markup=profile_menu_keyboard(),
        )
        await callback.answer()
        return

    await _send_reports_list(callback.message, reports)
    await callback.answer()


@router.callback_query(F.data.startswith(CB_COMPAT_DELETE_CONFIRM_PREFIX))
async def cb_delete_report_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.from_user is None or callback.data is None:
        await callback.answer()
        return

    report_id = UUID(callback.data.removeprefix(CB_COMPAT_DELETE_CONFIRM_PREFIX))
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await callback.answer()
        return

    deleted = await delete_compatibility_report_for_user(session, report_id, user.id)
    await session.commit()
    if not deleted:
        await callback.answer("Не получилось удалить", show_alert=True)
        return

    await callback.answer("Разбор удалён")
    reports = await compatibility_crud.list_compatibility_reports(session, user.id, limit=15)
    if not reports:
        await callback.message.answer(
            "Список пуст. Нажми «💕 Совместимость», чтобы создать новый разбор.",
            reply_markup=profile_menu_keyboard(),
        )
        return
    await _send_reports_list(callback.message, reports)


@router.callback_query(F.data.startswith(CB_COMPAT_DELETE_CANCEL_PREFIX))
async def cb_delete_report_cancel(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.answer("Оставила разбор как есть ✨")
    await callback.answer()


@router.callback_query(
    F.data.startswith(CB_COMPAT_DELETE_PREFIX)
    & ~F.data.startswith(CB_COMPAT_DELETE_CONFIRM_PREFIX)
    & ~F.data.startswith(CB_COMPAT_DELETE_CANCEL_PREFIX),
)
async def cb_delete_report_prompt(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.from_user is None or callback.data is None:
        await callback.answer()
        return

    report_id = UUID(callback.data.removeprefix(CB_COMPAT_DELETE_PREFIX))
    user = await users_crud.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await callback.answer()
        return

    report = await compatibility_crud.get_compatibility_report(session, report_id)
    if report is None or report.owner_user_id != user.id:
        await callback.answer("Разбор не найден", show_alert=True)
        return

    await callback.message.answer(
        f"Удалить разбор <b>{report.title}</b>?\n"
        "PDF исчезнет из списка — восстановить не получится.",
        parse_mode="HTML",
        reply_markup=compatibility_delete_confirm_keyboard(str(report.id)),
    )
    await callback.answer()
