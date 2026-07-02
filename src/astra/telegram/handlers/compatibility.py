"""FSM совместимости: контекст → режим → данные → PDF."""

from __future__ import annotations

import logging
from datetime import date, datetime
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from astra.compatibility.enums import PairMode, RelationshipContext
from astra.compatibility import crud as compatibility_crud
from astra.services.compatibility_service import (
    COMPATIBILITY_IN_PROGRESS_TEXT,
    CompatibilityRequestStatus,
    FsmPersonData,
    create_report_from_fsm,
    request_compatibility_report,
)
from astra.telegram.button_texts import (
    BTN_COMPATIBILITY,
    BTN_GENDER_FEMALE,
    BTN_GENDER_MALE,
    CB_COMPAT_CANCEL,
    CB_COMPAT_CONFIRM,
    CB_COMPAT_CONTEXT_PREFIX,
    CB_COMPAT_MODE_PREFIX,
    CB_COMPAT_REPORT_PREFIX,
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
    compatibility_pair_mode_keyboard,
    compatibility_reports_keyboard,
    gender_keyboard,
    main_menu_keyboard,
    profile_menu_keyboard,
    skip_keyboard,
)
from astra.telegram.states import CompatibilityStates
from astra.telegram.utils import parse_birth_date, parse_birth_time
from astra.users import crud as users_crud
from astra.users.gender import GENDER_FEMALE, GENDER_MALE

logger = logging.getLogger(__name__)

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
async def cb_choose_context(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer()
        return
    value = callback.data.removeprefix(CB_COMPAT_CONTEXT_PREFIX)
    if value == "back":
        await state.set_state(CompatibilityStates.choose_context)
        await callback.message.edit_text(
            "💕 <b>Совместимость</b>\n\nВыбери контекст разбора:",
            parse_mode="HTML",
            reply_markup=compatibility_context_keyboard(),
        )
        await callback.answer()
        return

    if value not in {c.value for c in RelationshipContext}:
        await callback.answer("Неизвестный контекст", show_alert=True)
        return

    await state.update_data(relationship_context=value)
    await state.set_state(CompatibilityStates.choose_pair_mode)
    await callback.message.edit_text(
        "Кто участвует в разборе?",
        reply_markup=compatibility_pair_mode_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith(CB_COMPAT_MODE_PREFIX))
async def cb_choose_pair_mode(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer()
        return
    value = callback.data.removeprefix(CB_COMPAT_MODE_PREFIX)
    if value not in {m.value for m in PairMode}:
        await callback.answer("Неизвестный режим", show_alert=True)
        return

    await state.update_data(pair_mode=value)
    if value == PairMode.ME_PARTNER:
        await state.update_data(collecting=COLLECTING_PERSON_B)
        await state.set_state(CompatibilityStates.collect_name)
        await callback.message.answer(
            "Данные о <b>тебе</b> возьму из профиля.\n\n"
            "Как зовут <b>партнёра</b>?",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await state.update_data(collecting=COLLECTING_PERSON_A)
        await state.set_state(CompatibilityStates.collect_name)
        await callback.message.answer(
            "Как зовут <b>первого человека</b>?",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove(),
        )
    await callback.answer()


@router.message(CompatibilityStates.collect_name)
async def collect_name(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if await _require_user(message, session) is None:
        return
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Введи имя (минимум 2 символа).")
        return
    data = await state.get_data()
    collecting = data.get("collecting", COLLECTING_PERSON_B)
    await state.update_data(**{f"{collecting}_name": name})
    await state.set_state(CompatibilityStates.collect_gender)
    await message.answer(
        f"Пол {_person_label(collecting)}:",
        reply_markup=gender_keyboard(),
    )


@router.message(CompatibilityStates.collect_gender, F.text.in_(GENDER_REPLY_BUTTONS))
async def collect_gender(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if await _require_user(message, session) is None:
        return
    data = await state.get_data()
    collecting = data.get("collecting", COLLECTING_PERSON_B)
    gender = GENDER_MALE if message.text == BTN_GENDER_MALE else GENDER_FEMALE
    await state.update_data(**{f"{collecting}_gender": gender})
    await state.set_state(CompatibilityStates.collect_birth_date)
    await message.answer(
        f"Дата рождения {_person_label(collecting)} (ДД.ММ.ГГГГ):",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(CompatibilityStates.collect_birth_date)
async def collect_birth_date(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if await _require_user(message, session) is None:
        return
    parsed = parse_birth_date(message.text or "")
    if parsed is None:
        await message.answer("Не разобрал дату. Формат: ДД.ММ.ГГГГ")
        return
    data = await state.get_data()
    collecting = data.get("collecting", COLLECTING_PERSON_B)
    await state.update_data(**{f"{collecting}_birth_date": parsed.isoformat()})
    await state.set_state(CompatibilityStates.collect_birth_time)
    await message.answer(
        f"Время рождения {_person_label(collecting)} (ЧЧ:ММ).\n"
        "Если не знаешь — нажми «⏭ Пропустить».",
        reply_markup=skip_keyboard(),
    )


@router.message(CompatibilityStates.collect_birth_time, F.text == SKIP_TIME_TEXT)
async def skip_birth_time(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if await _require_user(message, session) is None:
        return
    data = await state.get_data()
    collecting = data.get("collecting", COLLECTING_PERSON_B)
    await state.update_data(**{f"{collecting}_birth_time": None})
    await start_compatibility_birth_place_step(message, state, collecting=collecting)


@router.message(CompatibilityStates.collect_birth_time)
async def collect_birth_time(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if await _require_user(message, session) is None:
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
    await start_compatibility_birth_place_step(message, state, collecting=collecting)


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

    pair_mode = data.get("pair_mode", PairMode.ME_PARTNER)
    if pair_mode == PairMode.TWO_PEOPLE and collecting == COLLECTING_PERSON_A:
        await state.update_data(collecting=COLLECTING_PERSON_B)
        await state.set_state(CompatibilityStates.collect_name)
        await message.answer(
            "Теперь данные <b>второго человека</b>.\n\nКак его/её зовут?",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await _show_confirm(message, state)


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
        outcome = await request_compatibility_report(session, report.id, allow_async=True)
    except Exception:
        logger.exception("Failed to create compatibility report")
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
    else:
        await callback.message.answer(
            COMPATIBILITY_IN_PROGRESS_TEXT,
            reply_markup=main_menu_keyboard(),
        )
    await callback.answer()


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

    buttons: list[tuple[str, str]] = []
    for report in reports:
        status_icon = "✅" if report.pdf_path else "⏳"
        created = report.created_at.strftime("%d.%m") if report.created_at else ""
        label = f"{status_icon} {report.title} ({created})"
        buttons.append((label[:60], str(report.id)))

    await callback.message.answer(
        "📚 <b>Мои разборы</b>\nНажми, чтобы получить PDF ещё раз:",
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
async def cb_resend_report(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.from_user is None or callback.data is None:
        await callback.answer()
        return
    report_id = UUID(callback.data.removeprefix(CB_COMPAT_REPORT_PREFIX))
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
