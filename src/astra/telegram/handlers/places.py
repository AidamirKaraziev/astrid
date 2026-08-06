"""Выбор населённого пункта: поиск → список → онбординг или профиль."""

from uuid import UUID

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from astra.places import crud as places_crud
from astra.places.geonames_import import ensure_places_catalog
from astra.places.getters import get_place_read
from astra.core.observability import Event, get_logger
from astra.db.session import get_session_factory
from astra.services.greeting_service import run_greeting_phase
from astra.services.onboarding_service import parse_registration_fsm, run_registration_phase
from astra.telegram.keyboards import profile_menu_keyboard
from astra.telegram.states import (
    CompatibilityStates,
    NatalStates,
    OnboardingStates,
    PeopleStates,
    ProfileStates,
)
from astra.users import crud as users_crud
from astra.telegram.keyboards_places import (
    PAGE_SIZE,
    REGION_STEP_FROM,
    places_pick_keyboard,
    regions_pick_keyboard,
)

log = get_logger(__name__)

router = Router(name="places")

PLACE_STATES = (
    OnboardingStates.birth_place_query,
    ProfileStates.edit_notification_place_query,
    CompatibilityStates.birth_place_query,
    PeopleStates.edit_birth_place_query,
    NatalStates.new_birth_place_query,
)

SEARCH_HINT = (
    "Начни вводить название — <b>город, посёлок или деревня</b>.\n"
    "Например: <code>Каширское</code>, <code>Вырица</code>, <code>Алматы</code>\n\n"
    "<i>Своего села нет в списке — подойдёт любой город в пределах 100 км, "
    "на расчёт это не влияет.</i>"
)

PLACES_CATALOG_UNAVAILABLE_TEXT = (
    "Справочник городов временно недоступен. Попробуй через минуту."
)

NOTHING_FOUND_TEXT = (
    "Ничего не нашла. Уточни название или добавь регион.\n"
    "Пример: <code>Иваново, Тверская область</code>"
)

NOTIFICATION_PLACE_TITLE = (
    "🌍 Где ты сейчас живёшь?\n"
    "<i>Для бесплатных предсказаний в 09:00 по твоему времени</i>"
)


async def _ensure_places_ready(session: AsyncSession) -> bool:
    if await places_crud.count_places(session) > 0:
        return True
    return await ensure_places_catalog(get_session_factory())


def _context_key_for_state(state: str | None) -> str:
    if state == OnboardingStates.birth_place_query.state:
        return "birth"
    if state == CompatibilityStates.birth_place_query.state:
        return "compatibility"
    if state == PeopleStates.edit_birth_place_query.state:
        return "people"
    if state == NatalStates.new_birth_place_query.state:
        return "natal_new"
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


async def start_compatibility_birth_place_step(
    message: Message,
    state: FSMContext,
    *,
    collecting: str,
) -> None:
    await state.set_state(CompatibilityStates.birth_place_query)
    await state.update_data(place_context="compatibility", collecting=collecting)
    label = "первого человека" if collecting == "person_a" else "партнёра"
    await send_place_step_prompt(message, title=f"📍 Где родился(ась) {label}?")


async def start_people_birth_place_step(
    message: Message,
    state: FSMContext,
    *,
    label: str,
) -> None:
    await state.set_state(PeopleStates.edit_birth_place_query)
    await state.update_data(place_context="people")
    await send_place_step_prompt(message, title=f"📍 Где родился(ась) {label}?")


async def start_natal_new_birth_place_step(message: Message, state: FSMContext) -> None:
    await state.set_state(NatalStates.new_birth_place_query)
    await state.update_data(place_context="natal_new")
    await send_place_step_prompt(message, title="📍 Где родился(ась) этот человек?")


async def start_profile_notification_place_step(message: Message, state: FSMContext) -> None:
    await state.set_state(ProfileStates.edit_notification_place_query)
    await state.update_data(place_context="notification")
    await send_place_step_prompt(message, title=NOTIFICATION_PLACE_TITLE)


async def _keep_place_state(state: FSMContext, context_key: str) -> None:
    """Не дать выбору места уехать из своего сценария."""
    await state.update_data(place_context=context_key)
    current = await state.get_state()
    if context_key == "birth":
        await state.set_state(OnboardingStates.birth_place_query)
    elif context_key == "compatibility":
        await state.set_state(CompatibilityStates.birth_place_query)
    elif context_key == "people":
        await state.set_state(PeopleStates.edit_birth_place_query)
    elif context_key == "natal_new":
        await state.set_state(NatalStates.new_birth_place_query)
    elif current != ProfileStates.edit_notification_place_query.state:
        await state.set_state(ProfileStates.edit_notification_place_query)


async def _show_regions(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    search: places_crud.PreparedSearch,
    *,
    offset: int = 0,
) -> None:
    """Первый шаг: тёзок много, спрашиваем регион."""
    regions = await places_crud.regions_for(session, search, limit=PAGE_SIZE, offset=offset)
    total = await places_crud.count_regions_for(session, search)

    stored = (await state.get_data()).get("place_regions") or []
    known = list(stored)[:offset] + [hit.admin1_name for hit in regions]
    await state.update_data(place_regions=known, place_region=None, place_offset=offset)

    await message.answer(
        f"Нашла {search.total} мест с таким названием. В каком регионе твоё?",
        reply_markup=regions_pick_keyboard(regions, offset=offset, total=total),
    )


async def _show_places(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    search: places_crud.PreparedSearch,
    *,
    region: str | None = None,
    offset: int = 0,
) -> None:
    """Второй шаг (или единственный): сами населённые пункты."""
    places = await places_crud.places_for(
        session,
        search,
        limit=PAGE_SIZE,
        offset=offset,
        region=region,
    )
    if not places:
        await message.answer(NOTHING_FOUND_TEXT, parse_mode="HTML")
        return

    total = search.total if region is None else None
    await state.update_data(place_region=region, place_offset=offset)
    title = (
        "Выбери своё место — рядом указан ближайший город:"
        if region is not None
        else "Выбери населённый пункт из списка:"
    )
    await message.answer(
        title,
        reply_markup=places_pick_keyboard(
            places,
            with_region=region is None,
            offset=offset,
            total=total,
            inside_region=region is not None,
        ),
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

    search = await places_crud.prepare_search(session, query)
    if search is None:
        await message.answer(
            NOTHING_FOUND_TEXT,
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await _keep_place_state(state, context_key)
    await state.update_data(place_query=query)

    # Тёзок много — плоский список бесполезен: человек не отличит одну
    # «Ивановку» от другой и выберет не своё место рождения.
    if search.total > REGION_STEP_FROM and await places_crud.count_regions_for(session, search) > 1:
        await _show_regions(message, state, session, search)
        return
    await _show_places(message, state, session, search)


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
    log.warning(
        Event.PLACES_SEARCH_EMPTY,
        user_id=message.from_user.id if message.from_user else None,
        state=await state.get_state(),
        content_type=message.content_type,
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
    await state.update_data(place_regions=None, place_region=None, place_offset=0)
    current = await state.get_state()
    if current == OnboardingStates.birth_place_query.state:
        await start_birth_place_step(callback.message, state)
    elif current == ProfileStates.edit_notification_place_query.state:
        await start_profile_notification_place_step(callback.message, state)
    await callback.answer()


async def _restore_search(
    state: FSMContext,
    session: AsyncSession,
) -> places_crud.PreparedSearch | None:
    """Пересобрать поиск по запросу, сохранённому в шаге.

    Запрос лежит в FSM, а не в callback_data: там всего 64 байта, и длинное
    название туда не влезет.
    """
    query = (await state.get_data()).get("place_query")
    if not query:
        return None
    return await places_crud.prepare_search(session, str(query))


@router.callback_query(F.data.startswith("place:region:"))
async def cb_place_region(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Человек выбрал регион — показываем места внутри него."""
    if callback.message is None:
        await callback.answer()
        return

    data = await state.get_data()
    regions = data.get("place_regions") or []
    try:
        index = int(str(callback.data).split(":")[-1])
        region = regions[index]
    except (ValueError, IndexError):
        await callback.answer("Начни поиск заново")
        return

    search = await _restore_search(state, session)
    if search is None:
        await callback.message.answer(NOTHING_FOUND_TEXT, parse_mode="HTML")
        await callback.answer()
        return

    await _show_places(callback.message, state, session, search, region=region)
    await callback.answer()


@router.callback_query(F.data == "place:regions")
async def cb_place_back_to_regions(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    search = await _restore_search(state, session)
    if search is None:
        await callback.answer("Начни поиск заново")
        return
    await _show_regions(callback.message, state, session, search)
    await callback.answer()


@router.callback_query(F.data.startswith("place:page:"))
async def cb_place_page(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """«Ещё» — следующая страница мест или регионов."""
    if callback.message is None:
        await callback.answer()
        return

    try:
        offset = int(str(callback.data).split(":")[-1])
    except ValueError:
        await callback.answer()
        return

    search = await _restore_search(state, session)
    if search is None:
        await callback.answer("Начни поиск заново")
        return

    data = await state.get_data()
    region = data.get("place_region")
    if region is None and data.get("place_regions"):
        await _show_regions(callback.message, state, session, search, offset=offset)
    else:
        await _show_places(
            callback.message,
            state,
            session,
            search,
            region=str(region) if region else None,
            offset=offset,
        )
    await callback.answer()


async def _complete_onboarding_after_birth_place(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    fsm_data = await state.get_data()
    reg = parse_registration_fsm(fsm_data)
    if reg is None:
        await message.answer("Что-то пошло не так. Нажми /start")
        return

    user = await users_crud.get_user_by_id(session, reg.user_id)
    if user is None:
        await message.answer("Что-то пошло не так. Нажми /start")
        return

    await run_registration_phase(session, user, reg)
    await session.commit()
    await run_greeting_phase(message, state, user)


async def _save_profile_notification_place(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    place_id: UUID,
    *,
    actor_telegram_id: int,
) -> None:
    user = await users_crud.get_user_by_telegram_id(session, actor_telegram_id)
    if user is None or user.profile is None:
        await message.answer("Сначала: /start")
        return

    place = await get_place_read(session, place_id)
    if place is None:
        await message.answer("Место не найдено. Попробуй ввести название ещё раз.")
        return

    await users_crud.update_profile(
        session,
        user.profile,
        notification_place_id=place.id,
        city=place.display_name,
        timezone=place.timezone,
    )
    await state.clear()
    await message.answer(
        f"Город для уведомлений сохранён: <b>{place.display_name}</b> ({place.timezone}) ✨",
        parse_mode="HTML",
        reply_markup=profile_menu_keyboard(),
    )


async def _apply_place_selection(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    place_id: UUID,
    *,
    actor_telegram_id: int,
) -> None:
    place = await get_place_read(session, place_id)
    if place is None:
        await message.answer("Место не найдено. Попробуй ввести название ещё раз.")
        return

    current_state = await state.get_state()

    if current_state == OnboardingStates.birth_place_query.state:
        await state.update_data(
            birth_place_id=str(place.id),
            birth_place_display=place.display_name,
        )
        await _complete_onboarding_after_birth_place(message, state, session)
        return

    if current_state == ProfileStates.edit_notification_place_query.state:
        await _save_profile_notification_place(
            message,
            state,
            session,
            place_id,
            actor_telegram_id=actor_telegram_id,
        )
        return

    if current_state == CompatibilityStates.birth_place_query.state:
        from astra.telegram.handlers.compatibility import complete_person_birth_place

        await complete_person_birth_place(
            message,
            state,
            session,
            place_display=place.display_name,
            place_id=place.id,
            timezone=place.timezone,
            actor_telegram_id=actor_telegram_id,
        )
        return

    if current_state == PeopleStates.edit_birth_place_query.state:
        from astra.telegram.handlers.people import complete_people_birth_place

        await complete_people_birth_place(
            message,
            state,
            session,
            place_display=place.display_name,
            place_id=place.id,
            timezone=place.timezone,
            actor_telegram_id=actor_telegram_id,
        )
        return

    if current_state == NatalStates.new_birth_place_query.state:
        from astra.telegram.handlers.natal import complete_natal_new_birth_place

        await complete_natal_new_birth_place(
            message,
            state,
            session,
            place_display=place.display_name,
            place_id=place.id,
            timezone=place.timezone,
            actor_telegram_id=actor_telegram_id,
        )
        return

    await message.answer("Что-то пошло не так. Нажми /start")


@router.callback_query(F.data.startswith("place:pick:"))
async def cb_place_pick(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    place_id = UUID(callback.data.split(":")[-1])
    await _apply_place_selection(
        callback.message,
        state,
        session,
        place_id,
        actor_telegram_id=callback.from_user.id,
    )
    await callback.answer()
