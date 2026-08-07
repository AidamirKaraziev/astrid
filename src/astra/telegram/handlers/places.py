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
from astra.core.config import get_settings
from astra.core.observability import Event, get_logger
from astra.db.session import get_session_factory
from astra.support import crud as support_crud
from astra.support.service import build_missing_place_card
from astra.telegram.keyboards import profile_menu_keyboard
from astra.telegram.states import (
    CompatibilityStates,
    NatalStates,
    BirthDataStates,
    PeopleStates,
    PlaceStates,
    ProfileStates,
)
from astra.users import crud as users_crud
from astra.users.gender import GENDER_FEMALE, GENDER_MALE, Gender, normalize_gender
from astra.telegram.keyboards_places import (
    PAGE_SIZE,
    REGION_STEP_FROM,
    missing_place_keyboard,
    nothing_found_keyboard,
    places_pick_keyboard,
    regions_pick_keyboard,
)

log = get_logger(__name__)

router = Router(name="places")

PLACE_STATES = (
    BirthDataStates.place_query,
    ProfileStates.edit_notification_place_query,
    CompatibilityStates.birth_place_query,
    PeopleStates.edit_birth_place_query,
    NatalStates.new_birth_place_query,
)

SEARCH_HINT = (
    "Начни вводить название — <b>город, посёлок или деревня</b>.\n"
    "Например: <code>Каширское</code>, <code>Вырица</code>, <code>Алматы</code>\n\n"
    "<i>Своего села нет в списке — подойдёт ближайший город в своей области, "
    "на расчёт это не влияет.</i>"
)

PLACES_CATALOG_UNAVAILABLE_TEXT = (
    "Справочник городов временно недоступен. Попробуй через минуту."
)

NOTHING_FOUND_TEXT = (
    "Ничего не нашла. Уточни название или добавь регион.\n"
    "Пример: <code>Иваново, Тверская область</code>"
)

# Почему 70 км, а не «как можно ближе»: сдвиг на 70 км двигает карту на 1,1°,
# это примерно как ошибиться во времени рождения на четыре минуты. А обычная
# неточность записанного времени — десять-пятнадцать минут, то есть погрешность
# места тонет в ней целиком. Настоящее ограничение не километры, а часовой
# пояс — в России он совпадает с границей региона, поэтому говорим «в своей
# области», а про пояса не упоминаем вовсе.
NEARBY_CITY_KM = 70

# Короче этого рассказ бесполезен: «нет города» оператору ничего не даёт.
_MIN_DESCRIPTION_LENGTH = 12

MISSING_PLACE_TEXT = (
    "Маленькие сёла и хутора есть в справочнике не всегда — и на разбор "
    "это не влияет.\n\n"
    "Карта считается по координатам места. Соседний город в пределах "
    f"{NEARBY_CITY_KM} км сдвигает её меньше, чем обычная неточность во "
    "времени рождения: разбор будет таким же точным.\n\n"
    "Выбери ближайший город <b>в своей области</b> — и продолжим."
)

DESCRIBE_PLACE_PROMPT = (
    "Расскажи одним сообщением, какого места не хватает:\n\n"
    "• название села, хутора или посёлка\n"
    "• район и область\n"
    "• страна\n"
    "• рядом с каким городом и сколько километров\n\n"
    "Например: <code>хутор Весёлый, Успенский район, Краснодарский край, "
    "15 км от Армавира</code>"
)

DESCRIBE_PLACE_ACCEPTED = (
    "Спасибо, передала команде 💜\nПроверим и добавим.\n\n"
    "Сейчас выбери ближайший город в своей области — разбор от этого "
    "не потеряет в точности."
)

DESCRIBE_PLACE_TOO_SHORT = (
    "Напиши чуть подробнее: название места, район и область, "
    "рядом с каким городом 💜"
)

NOTIFICATION_PLACE_TITLE = (
    "🌍 Где ты сейчас живёшь?\n"
    "<i>Для бесплатных предсказаний в 09:00 по твоему времени</i>"
)

# Запасной заголовок шага: сюда попадают карточка для оператора и возврат из
# рассказа о нехватке места, где пол взять неоткуда. Формы без рода — не
# «родился(ась)»: скобки и слэш — это бланк, а не речь.
_STEP_TITLES = {
    "birth": "📍 Где твоё место рождения?",
    "compatibility": "📍 Где место рождения этого человека?",
    "people": "📍 Где место рождения этого человека?",
    "natal_new": "📍 Где место рождения этого человека?",
    "notification": NOTIFICATION_PLACE_TITLE,
}

# Заголовок, который уже показали человеку: возврат к шагу должен повторить его
# слово в слово, иначе род поедет.
_PLACE_TITLE_KEY = "place_title"


def birth_place_question(gender: Gender | None, who: str | None = None) -> str:
    """Вопрос про место рождения в роде того, о ком спрашиваем.

    `who` — имя или подпись человека; None — спрашиваем про самого собеседника.
    Пол не задан — берём формулировку, в которой рода нет вовсе.
    """
    if who is None:
        if gender == GENDER_FEMALE:
            return "📍 Где ты родилась?"
        if gender == GENDER_MALE:
            return "📍 Где ты родился?"
        return "📍 Где твоё место рождения?"
    if gender == GENDER_FEMALE:
        return f"📍 Где родилась {who}?"
    if gender == GENDER_MALE:
        return f"📍 Где родился {who}?"
    return "📍 Где место рождения этого человека?"


async def _ensure_places_ready(session: AsyncSession) -> bool:
    if await places_crud.count_places(session) > 0:
        return True
    return await ensure_places_catalog(get_session_factory())


def _context_key_for_state(state: str | None) -> str:
    if state == BirthDataStates.place_query.state:
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


async def start_own_birth_place_step(
    message: Message,
    state: FSMContext,
    *,
    gender: Gender | None = None,
) -> None:
    """Место рождения самого пользователя — спрашивается посреди продукта.

    Раньше этот шаг был частью онбординга; теперь в него попадают из разбора
    или совместимости, когда в профиле места не оказалось.
    """
    title = birth_place_question(gender)
    await state.set_state(BirthDataStates.place_query)
    await state.update_data(place_context="birth", **{_PLACE_TITLE_KEY: title})
    await send_place_step_prompt(message, title=title)


async def start_compatibility_birth_place_step(
    message: Message,
    state: FSMContext,
    *,
    collecting: str,
) -> None:
    # Пол этого человека уже спросили шагом раньше — берём его из состояния,
    # а не гадаем. Подписи в именительном падеже: они подставляются в «Где
    # родился …», где родительный сломал бы фразу.
    data = await state.get_data()
    gender = normalize_gender(data.get(f"{collecting}_gender"))
    label = "первый человек" if collecting == "person_a" else "партнёр"
    title = birth_place_question(gender, who=label)
    await state.set_state(CompatibilityStates.birth_place_query)
    await state.update_data(
        place_context="compatibility",
        collecting=collecting,
        **{_PLACE_TITLE_KEY: title},
    )
    await send_place_step_prompt(message, title=title)


async def start_people_birth_place_step(
    message: Message,
    state: FSMContext,
    *,
    label: str,
    gender: Gender | None = None,
) -> None:
    title = birth_place_question(gender, who=label)
    await state.set_state(PeopleStates.edit_birth_place_query)
    await state.update_data(place_context="people", **{_PLACE_TITLE_KEY: title})
    await send_place_step_prompt(message, title=title)


async def start_natal_new_birth_place_step(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    gender = normalize_gender(data.get("natal_new_gender"))
    title = birth_place_question(gender, who=str(data.get("natal_new_name") or "").strip() or None)
    await state.set_state(NatalStates.new_birth_place_query)
    await state.update_data(place_context="natal_new", **{_PLACE_TITLE_KEY: title})
    await send_place_step_prompt(message, title=title)


async def start_profile_notification_place_step(message: Message, state: FSMContext) -> None:
    await state.set_state(ProfileStates.edit_notification_place_query)
    await state.update_data(place_context="notification")
    await send_place_step_prompt(message, title=NOTIFICATION_PLACE_TITLE)


async def _keep_place_state(state: FSMContext, context_key: str) -> None:
    """Не дать выбору места уехать из своего сценария."""
    await state.update_data(place_context=context_key)
    current = await state.get_state()
    if context_key == "birth":
        await state.set_state(BirthDataStates.place_query)
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

    # Запоминаем запрос до поиска, а не после: если не нашлось ничего, он и
    # нужен больше всего — именно его увидит оператор в карточке.
    await state.update_data(place_query=query)

    search = await places_crud.prepare_search(session, query)
    if search is None:
        # Даже здесь не оставляем человека без выхода: кнопка «не нашла свой
        # город» должна быть под руками, а не только под списком.
        await message.answer(
            NOTHING_FOUND_TEXT,
            parse_mode="HTML",
            reply_markup=nothing_found_keyboard(),
        )
        return

    await _keep_place_state(state, context_key)

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


async def _report_missing_place(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    text: str,
) -> None:
    """Положить рассказ о недостающем месте карточкой в админ-группу.

    Ошибка здесь никогда не должна ронять онбординг: человек и так уже не
    нашёл своё село, оставить его ещё и без ответа — верный способ потерять
    его совсем. Поэтому всё под `try`, а человек в любом случае возвращается
    к выбору города.
    """
    settings = get_settings()
    admin_chat_id = settings.telegram_admin_group_id
    if admin_chat_id == 0 or message.bot is None or message.from_user is None:
        log.warning(Event.SUPPORT_TICKET_CARD_FAILED, stage="missing_place_no_channel")
        return

    data = await state.get_data()
    searched = data.get("place_query")
    region = data.get("place_region")
    step = _STEP_TITLES.get(str(data.get("place_context") or ""), "место рождения")

    telegram_id = message.from_user.id
    user = await users_crud.get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return

    found: int | None = None
    if searched:
        search = await places_crud.prepare_search(session, str(searched))
        found = search.total if search else 0

    def card(number: int | None) -> str:
        return build_missing_place_card(
            number=number,
            display_name=user.profile.display_name if user.profile else "",
            telegram_id=telegram_id,
            username=message.from_user.username,
            searched=str(searched) if searched else None,
            region=str(region) if region else None,
            found=found,
            step=step.splitlines()[0],
            text=text,
        )

    try:
        card_msg = await message.bot.send_message(admin_chat_id, card(None))
        ticket = await support_crud.create_ticket(
            session,
            user_id=user.id,
            telegram_id=telegram_id,
            admin_chat_id=admin_chat_id,
            admin_message_id=card_msg.message_id,
            last_message=text,
        )
        try:
            await message.bot.edit_message_text(
                card(ticket.number),
                chat_id=admin_chat_id,
                message_id=card_msg.message_id,
            )
        except Exception:
            log.warning(Event.SUPPORT_TICKET_CARD_FAILED, stage="missing_place_number")
        log.info(
            Event.SUPPORT_TICKET_CREATED,
            ticket=ticket.number,
            user_id=str(user.id),
            kind="missing_place",
            searched=str(searched) if searched else None,
        )
    except Exception:
        log.exception(Event.SUPPORT_TICKET_CARD_FAILED, stage="missing_place_send")


async def _restart_place_step(message: Message, state: FSMContext) -> None:
    """Спросить место заново, вернув человека в тот же сценарий.

    Заголовок берём по контексту: из выбора места человек попадает сюда и из
    онбординга, и из совместимости, и из «моих людей».
    """
    data = await state.get_data()
    context_key = str(data.get("place_context") or "birth")
    title = str(data.get(_PLACE_TITLE_KEY) or "").strip()
    await state.update_data(place_regions=None, place_region=None, place_offset=0)
    await _keep_place_state(state, context_key)
    await send_place_step_prompt(
        message,
        title=title or _STEP_TITLES.get(context_key, "📍 Где это место?"),
    )


@router.callback_query(F.data == "place:retry")
async def cb_place_retry(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await _restart_place_step(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "place:missing")
async def cb_place_missing(callback: CallbackQuery, state: FSMContext) -> None:
    """«Не нашла свой город» — сначала снимаем тревогу, потом предлагаем помочь."""
    if callback.message is None:
        await callback.answer()
        return
    await callback.message.answer(
        MISSING_PLACE_TEXT,
        parse_mode="HTML",
        reply_markup=missing_place_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "place:describe")
async def cb_place_describe(callback: CallbackQuery, state: FSMContext) -> None:
    """Человек согласился рассказать, какого места не хватает."""
    if callback.message is None:
        await callback.answer()
        return
    data = await state.get_data()
    # Запоминаем, откуда забрали: после рассказа надо вернуть ровно туда.
    await state.update_data(place_context=str(data.get("place_context") or "birth"))
    await state.set_state(PlaceStates.describing_missing)
    await callback.message.answer(DESCRIBE_PLACE_PROMPT, parse_mode="HTML")
    await callback.answer()


@router.message(PlaceStates.describing_missing)
async def receive_missing_place(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Рассказ о недостающем месте → карточка в админ-группу → назад к выбору."""
    text = (message.text or message.caption or "").strip()
    if len(text) < _MIN_DESCRIPTION_LENGTH:
        await message.answer(DESCRIBE_PLACE_TOO_SHORT)
        return

    await _report_missing_place(message, state, session, text)
    await message.answer(DESCRIBE_PLACE_ACCEPTED)
    await _restart_place_step(message, state)


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


async def _save_own_birth_place(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    place,  # noqa: ANN001 — PlaceRead
    *,
    actor_telegram_id: int,
) -> None:
    """Записать место рождения в профиль и вернуть человека в продукт."""
    from astra.telegram.birth_data_gate import continue_after_birth_data

    user = await users_crud.get_user_by_telegram_id(session, actor_telegram_id)
    if user is None or user.profile is None:
        await message.answer("Сначала давай познакомимся — жми /start ✨")
        return

    updates: dict[str, object] = {
        "birth_place_id": place.id,
        "birth_place": place.display_name,
    }
    # Город и пояс для ежедневной рассылки берём отсюда же, пока человек не
    # выбрал город уведомлений сам: иначе предсказание уходило бы в 09:00 по
    # Москве тому, кто живёт во Владивостоке.
    if user.profile.notification_place_id is None:
        updates["city"] = place.display_name
        updates["timezone"] = place.timezone

    await users_crud.update_profile(session, user.profile, **updates)
    await session.commit()
    await continue_after_birth_data(message, state, session, user)


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
        await message.answer("Сначала давай познакомимся — жми /start ✨")
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

    if current_state == BirthDataStates.place_query.state:
        await _save_own_birth_place(
            message,
            state,
            session,
            place,
            actor_telegram_id=actor_telegram_id,
        )
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

    await message.answer("Что-то сбилось. Начнём заново — жми /start")


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
