"""Выбор населённого пункта: поиск → список → подтверждение."""

import logging
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from astra.places import crud as places_crud
from astra.places.geonames_import import ensure_places_catalog
from astra.places.getters import format_place_confirm, get_place_read
from astra.db.session import get_session_factory
from astra.telegram.keyboards_places import place_confirm_keyboard, places_pick_keyboard
from astra.telegram.states import OnboardingStates

logger = logging.getLogger(__name__)

router = Router(name="places")

PLACE_STATES = (
    OnboardingStates.birth_place_query,
    OnboardingStates.notification_place_query,
)

SEARCH_HINT = (
    "Начни вводить название — <b>город, посёлок или деревня</b> в России.\n"
    "Например: <code>Каширское</code>, <code>Вырица</code>, <code>Казань</code>"
)

PLACES_CATALOG_UNAVAILABLE_TEXT = (
    "Справочник городов временно недоступен. Попробуй через минуту."
)


async def _ensure_places_ready(session: AsyncSession) -> bool:
    if await places_crud.count_places(session) > 0:
        return True
    return await ensure_places_catalog(get_session_factory())


def _context_key_for_state(state: str | None) -> str:
    if state == OnboardingStates.birth_place_query.state:
        return "birth"
    return "notification"


async def _places_catalog_empty(session: AsyncSession) -> bool:
    return not await _ensure_places_ready(session)


async def send_place_step_prompt(message: Message, *, title: str) -> None:
    await message.answer(
        f"{title}\n\n{SEARCH_HINT}",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )


async def start_birth_place_step(message: Message, state: FSMContext) -> None:
    await state.set_state(OnboardingStates.birth_place_query)
    await state.update_data(place_context="birth")
    await send_place_step_prompt(message, title="📍 Где ты родилась?")


async def start_notification_place_step(message: Message, state: FSMContext) -> None:
    await state.set_state(OnboardingStates.notification_place_query)
    await state.update_data(place_context="notification")
    await send_place_step_prompt(
        message,
        title="🌍 Где ты сейчас живёшь? (для бесплатных предсказаний в 09:00 по твоему времени)",
    )


async def handle_place_query(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    *,
    context_key: str,
) -> None:
    query = (message.text or "").strip()
    if len(query) < 2:
        await message.answer(
            "Введи минимум 2 символа названия города.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if await _places_catalog_empty(session):
        await message.answer(
            PLACES_CATALOG_UNAVAILABLE_TEXT,
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    places = await places_crud.search_places(session, query)
    if not places:
        await message.answer(
            "Ничего не нашла. Уточни название или добавь регион.\n"
            "Пример: <code>Иваново, Тверская область</code>",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await state.update_data(place_context=context_key)
    if context_key == "birth":
        await state.set_state(OnboardingStates.birth_place_query)
    else:
        await state.set_state(OnboardingStates.notification_place_query)
    await message.answer(
        "Выбери населённый пункт из списка:",
        reply_markup=places_pick_keyboard(places),
    )


@router.message(StateFilter(*PLACE_STATES), F.text)
async def place_text_search(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    context_key = _context_key_for_state(await state.get_state())
    await handle_place_query(message, state, session, context_key=context_key)


@router.message(StateFilter(*PLACE_STATES))
async def place_step_fallback(message: Message, state: FSMContext) -> None:
    logger.warning(
        "Unhandled place step: user=%s state=%s content_type=%s text=%r",
        message.from_user.id if message.from_user else None,
        await state.get_state(),
        message.content_type,
        message.text,
    )
    await message.answer(
        "Введи <b>название города</b> текстом в поле ввода.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.callback_query(F.data == "place:retry")
async def cb_place_retry(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return
    current = await state.get_state()
    if current == OnboardingStates.birth_place_query.state:
        await start_birth_place_step(callback.message, state)
    elif current == OnboardingStates.notification_place_query.state:
        await start_notification_place_step(callback.message, state)
    await callback.answer()


@router.callback_query(F.data.startswith("place:pick:"))
async def cb_place_pick(callback: CallbackQuery, session: AsyncSession) -> None:
    place_id = UUID(callback.data.split(":")[-1])
    place = await get_place_read(session, place_id)
    if place is None or callback.message is None:
        await callback.answer("Место не найдено", show_alert=True)
        return
    await callback.message.answer(
        "Это правильное место?\n\n" + format_place_confirm(place),
        parse_mode="HTML",
        reply_markup=place_confirm_keyboard(place_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("place:confirm:"))
async def cb_place_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    from astra.telegram.handlers.onboarding import finish_onboarding

    place_id = UUID(callback.data.split(":")[-1])
    place = await get_place_read(session, place_id)
    if place is None:
        await callback.answer("Место не найдено", show_alert=True)
        return

    current_state = await state.get_state()

    if current_state == OnboardingStates.birth_place_query.state:
        await state.update_data(
            birth_place_id=str(place.id),
            birth_place_display=place.display_name,
        )
        if callback.message:
            await start_notification_place_step(callback.message, state)
        await callback.answer()
        return

    if current_state == OnboardingStates.notification_place_query.state:
        await state.update_data(
            notification_place_id=str(place.id),
            notification_place_display=place.display_name,
            notification_timezone=place.timezone,
        )
        if callback.message:
            await finish_onboarding(callback.message, state, session)
        await callback.answer()
        return

    await callback.answer()
