"""Выбор населённого пункта: поиск → список → подтверждение."""

import logging
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.places import crud as places_crud
from astra.places.geonames_import import ensure_places_catalog
from astra.places.geolocation import find_nearest_places
from astra.places.getters import format_place_confirm, get_place_read
from astra.places.schemas import PlaceRead
from astra.db.session import get_session_factory
from astra.telegram.keyboards_places import (
    BTN_SEND_LOCATION,
    BTN_TYPE_PLACE_NAME,
    LOCATION_BUTTON_TEXTS,
    PLACE_KEYBOARD_BUTTON_TEXTS,
    place_confirm_keyboard,
    place_step_reply_keyboard,
    places_pick_keyboard,
)
from astra.telegram.webapp import parse_webapp_location_payload
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

GEOLOCATION_FAILED_TEXT = "Не смог получить твою геопозицию, введи название в ручную"

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


async def reply_geolocation_failed(message: Message) -> None:
    await message.answer(
        GEOLOCATION_FAILED_TEXT,
        reply_markup=place_step_reply_keyboard(),
    )


async def send_place_step_prompt(message: Message, state: FSMContext, *, title: str) -> None:
    await message.answer(
        f"{title}\n\n"
        f"• <b>«{BTN_SEND_LOCATION}»</b> — на телефоне\n"
        "• Или введи название в поле ввода",
        parse_mode="HTML",
        reply_markup=place_step_reply_keyboard(),
    )


async def start_birth_place_step(message: Message, state: FSMContext) -> None:
    await state.set_state(OnboardingStates.birth_place_query)
    await state.update_data(place_context="birth")
    await send_place_step_prompt(message, state, title="📍 Где ты родилась?")


async def start_notification_place_step(message: Message, state: FSMContext) -> None:
    await state.set_state(OnboardingStates.notification_place_query)
    await state.update_data(place_context="notification")
    await send_place_step_prompt(
        message,
        state,
        title="🌍 Где ты сейчас живёшь? (для бесплатных предсказаний в 09:00 по твоему времени)",
    )


async def handle_place_location(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    *,
    context_key: str,
) -> None:
    if message.location is None:
        await reply_geolocation_failed(message)
        return

    try:
        await handle_place_coordinates(
            message,
            state,
            session,
            latitude=message.location.latitude,
            longitude=message.location.longitude,
            context_key=context_key,
        )
    except Exception:
        logger.exception("handle_place_location failed")
        await reply_geolocation_failed(message)


async def handle_place_coordinates(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    *,
    latitude: float,
    longitude: float,
    context_key: str,
) -> None:
    if await _places_catalog_empty(session):
        await message.answer(
            PLACES_CATALOG_UNAVAILABLE_TEXT,
            reply_markup=place_step_reply_keyboard(),
        )
        return

    logger.info(
        "Geolocation lat=%s lon=%s user=%s context=%s",
        latitude,
        longitude,
        message.from_user.id if message.from_user else None,
        context_key,
    )

    nearest = await find_nearest_places(session, latitude, longitude)
    if not nearest:
        await reply_geolocation_failed(message)
        return

    place, distance_km = nearest[0]
    place_read = PlaceRead.model_validate(place)

    await state.update_data(place_context=context_key)
    if context_key == "birth":
        await state.set_state(OnboardingStates.birth_place_query)
    else:
        await state.set_state(OnboardingStates.notification_place_query)

    dist_str = f"{distance_km:.1f} км" if distance_km >= 1 else f"{int(distance_km * 1000)} м"
    await message.answer(
        f"По геолокации ближайший населённый пункт (~{dist_str}):\n\n"
        + format_place_confirm(place_read)
        + "\n\n<i>Если это не то — введи название вручную.</i>",
        parse_mode="HTML",
        reply_markup=place_confirm_keyboard(place.id),
    )


async def handle_place_webapp_data(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.web_app_data is None:
        return
    coords = parse_webapp_location_payload(message.web_app_data.data)
    if coords is None:
        await reply_geolocation_failed(message)
        return
    lat, lon = coords
    context_key = _context_key_for_state(await state.get_state())
    try:
        await handle_place_coordinates(
            message,
            state,
            session,
            latitude=lat,
            longitude=lon,
            context_key=context_key,
        )
    except Exception:
        logger.exception("handle_place_webapp_data failed")
        await reply_geolocation_failed(message)


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
            reply_markup=place_step_reply_keyboard(),
        )
        return

    if await _places_catalog_empty(session):
        await message.answer(
            PLACES_CATALOG_UNAVAILABLE_TEXT,
            reply_markup=place_step_reply_keyboard(),
        )
        return

    places = await places_crud.search_places(session, query)
    if not places:
        await message.answer(
            "Ничего не нашла. Уточни название или добавь регион.\n"
            "Пример: <code>Иваново, Тверская область</code>",
            parse_mode="HTML",
            reply_markup=place_step_reply_keyboard(),
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


@router.message(StateFilter(*PLACE_STATES), F.web_app_data)
async def place_webapp_location(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await handle_place_webapp_data(message, state, session)


@router.message(StateFilter(*PLACE_STATES), F.location)
async def place_location_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    context_key = _context_key_for_state(await state.get_state())
    await handle_place_location(message, state, session, context_key=context_key)


@router.message(StateFilter(*PLACE_STATES), F.text == BTN_TYPE_PLACE_NAME)
async def place_manual_hint(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    title = (
        "📍 Где ты родилась?"
        if current == OnboardingStates.birth_place_query.state
        else "🌍 Где ты сейчас живёшь?"
    )
    await message.answer(
        f"{title}\n\n{SEARCH_HINT}",
        parse_mode="HTML",
        reply_markup=place_step_reply_keyboard(),
    )


@router.message(StateFilter(*PLACE_STATES), F.text.in_(LOCATION_BUTTON_TEXTS))
async def place_location_button_text(message: Message) -> None:
    """Desktop: request_location приходит как текст, координат нет."""
    await reply_geolocation_failed(message)


@router.message(
    StateFilter(*PLACE_STATES),
    F.text,
    ~F.text.in_(PLACE_KEYBOARD_BUTTON_TEXTS),
)
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
        "Отправь <b>геолокацию</b> кнопкой ниже или <b>введи название города</b> вручную.",
        parse_mode="HTML",
        reply_markup=place_step_reply_keyboard(),
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
