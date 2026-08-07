"""FSM разбора натала: время спрашивается только при отсутствии, путь «не знаю»."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from astra.telegram.button_texts import BTN_NATAL
from astra.telegram.handlers.natal import (
    CB_NATAL_SUBJECT_ALL,
    CB_NATAL_SUBJECT_PICK_PREFIX,
    _subject_keyboard,
    cb_natal_confirm,
    cb_natal_subject_new,
    cb_natal_subject_pick,
    cb_natal_subject_self,
    collect_birth_time,
    collect_new_name,
    complete_natal_new_birth_place,
    start_natal,
)
from astra.telegram.states import NatalStates


async def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=2, user_id=3)
    return FSMContext(storage=storage, key=key)


def _user(*, birth_time: datetime | None) -> MagicMock:
    user = MagicMock()
    user.onboarding_completed = True
    profile = MagicMock()
    profile.display_name = "Айдамир"
    profile.birth_date = date(1990, 6, 15)
    profile.birth_time = birth_time
    profile.birth_place = "Москва"
    user.profile = profile
    return user


def _message() -> AsyncMock:
    message = AsyncMock()
    message.text = BTN_NATAL
    message.answer = AsyncMock()
    message.from_user = MagicMock()
    message.from_user.id = 42
    return message


@pytest.mark.anyio
async def test_start_natal_always_shows_picker_without_profiles() -> None:
    # даже без сохранённых людей показываем выбор «Для меня / Новый человек»
    state = await _fsm_context()
    message = _message()
    session = AsyncMock()

    with (
        patch(
            "astra.telegram.handlers.natal.users_crud.get_user_by_telegram_id",
            new=AsyncMock(return_value=_user(birth_time=None)),
        ),
        patch(
            "astra.telegram.handlers.natal.compatibility_crud.list_natal_profiles",
            new=AsyncMock(return_value=[]),
        ),
    ):
        await start_natal(message, state, session)

    assert await state.get_state() is None
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    assert "natal:subject:self" in callbacks
    assert "natal:subject:new" in callbacks


@pytest.mark.anyio
async def test_self_flow_asks_time_when_missing() -> None:
    state = await _fsm_context()
    callback = _callback("natal:subject:self")
    session = AsyncMock()

    with patch(
        "astra.telegram.handlers.natal.users_crud.get_user_by_telegram_id",
        new=AsyncMock(return_value=_user(birth_time=None)),
    ):
        await cb_natal_subject_self(callback, state, session)

    assert await state.get_state() == NatalStates.collect_birth_time.state
    text = callback.message.answer.await_args.args[0]
    assert "временем рождения" in text.lower()


@pytest.mark.anyio
async def test_self_flow_skips_time_when_present() -> None:
    state = await _fsm_context()
    callback = _callback("natal:subject:self")
    session = AsyncMock()

    with patch(
        "astra.telegram.handlers.natal.users_crud.get_user_by_telegram_id",
        new=AsyncMock(return_value=_user(birth_time=datetime(1990, 6, 15, 14, 30))),
    ):
        await cb_natal_subject_self(callback, state, session)

    assert await state.get_state() == NatalStates.confirm.state
    text = callback.message.answer.await_args.args[0]
    assert "14:30" in text
    assert "Без времени рождения" not in text


@pytest.mark.anyio
async def test_self_flow_invalid_time_stays_in_collect() -> None:
    state = await _fsm_context()
    callback = _callback("natal:subject:self")
    message = _message()
    session = AsyncMock()

    with patch(
        "astra.telegram.handlers.natal.users_crud.get_user_by_telegram_id",
        new=AsyncMock(return_value=_user(birth_time=None)),
    ):
        await cb_natal_subject_self(callback, state, session)
        message.text = "abc"
        await collect_birth_time(message, state, session)

    # невалидное время — остаёмся в состоянии сбора
    assert await state.get_state() == NatalStates.collect_birth_time.state


@pytest.mark.anyio
async def test_collect_birth_time_saves_and_confirms() -> None:
    state = await _fsm_context()
    await state.set_state(NatalStates.collect_birth_time)
    message = _message()
    message.text = "14:30"
    session = AsyncMock()
    user = _user(birth_time=None)

    with (
        patch(
            "astra.telegram.handlers.natal.users_crud.get_user_by_telegram_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "astra.telegram.handlers.natal.users_crud.update_profile",
            new=AsyncMock(),
        ) as update_mock,
    ):
        await collect_birth_time(message, state, session)

    update_mock.assert_awaited_once()
    saved = update_mock.await_args.kwargs["birth_time"]
    assert saved == datetime(1990, 6, 15, 14, 30)
    assert await state.get_state() == NatalStates.confirm.state


def _natal_profile(owner_id, *, birth_time: datetime | None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        owner_user_id=owner_id,
        label="Анжела",
        gender="женщина",
        birth_date=date(1995, 6, 20),
        birth_time=birth_time,
        birth_place="Москва",
        birth_place_id=uuid4(),
        timezone="Europe/Moscow",
    )


def _callback(data: str) -> AsyncMock:
    callback = AsyncMock()
    callback.data = data
    callback.answer = AsyncMock()
    callback.from_user = MagicMock()
    callback.from_user.id = 42
    callback.message = AsyncMock()
    callback.message.answer = AsyncMock()
    return callback


@pytest.mark.anyio
async def test_start_natal_shows_subject_picker_when_profiles_exist() -> None:
    state = await _fsm_context()
    message = _message()
    session = AsyncMock()
    user = _user(birth_time=datetime(1990, 6, 15, 14, 30))
    user.id = uuid4()

    with (
        patch(
            "astra.telegram.handlers.natal.users_crud.get_user_by_telegram_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "astra.telegram.handlers.natal.compatibility_crud.list_natal_profiles",
            new=AsyncMock(return_value=[_natal_profile(user.id, birth_time=None)]),
        ),
    ):
        await start_natal(message, state, session)

    # показан выбор субъекта, во флоу времени/подтверждения не ушли
    assert await state.get_state() is None
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    texts = [btn.text for row in keyboard.inline_keyboard for btn in row]
    assert "🙋 Разбор для меня" in texts
    assert any("Анжела" in t for t in texts)


@pytest.mark.anyio
async def test_pick_subject_with_time_goes_to_confirm() -> None:
    state = await _fsm_context()
    session = AsyncMock()
    user = _user(birth_time=datetime(1990, 6, 15, 14, 30))
    user.id = uuid4()
    profile = _natal_profile(user.id, birth_time=datetime(1995, 6, 20, 9, 15))
    callback = _callback(f"{CB_NATAL_SUBJECT_PICK_PREFIX}{profile.id}")

    with (
        patch(
            "astra.telegram.handlers.natal.users_crud.get_user_by_telegram_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "astra.telegram.handlers.natal.compatibility_crud.get_natal_profile_by_id",
            new=AsyncMock(return_value=profile),
        ),
    ):
        await cb_natal_subject_pick(callback, state, session)

    assert await state.get_state() == NatalStates.confirm.state
    data = await state.get_data()
    assert data["natal_subject_profile_id"] == str(profile.id)
    text = callback.message.answer.await_args.args[0]
    assert "Анжела" in text


@pytest.mark.anyio
async def test_confirm_for_subject_calls_subject_creator() -> None:
    state = await _fsm_context()
    session = AsyncMock()
    user = _user(birth_time=datetime(1990, 6, 15, 14, 30))
    user.id = uuid4()
    profile = _natal_profile(user.id, birth_time=datetime(1995, 6, 20, 9, 15))
    await state.set_state(NatalStates.confirm)
    await state.update_data(natal_subject_profile_id=str(profile.id))
    callback = _callback("natal:confirm")

    report = MagicMock()
    report.id = uuid4()

    with (
        patch(
            "astra.telegram.handlers.natal.users_crud.get_user_by_telegram_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "astra.telegram.handlers.natal.compatibility_crud.get_natal_profile_by_id",
            new=AsyncMock(return_value=profile),
        ),
        patch(
            "astra.telegram.handlers.natal.create_natal_report_for_subject",
            new=AsyncMock(return_value=report),
        ) as subject_mock,
        patch(
            "astra.telegram.handlers.natal.create_natal_report_for_user",
            new=AsyncMock(),
        ) as user_mock,
        patch(
            "astra.telegram.handlers.natal.request_natal_report",
            new=AsyncMock(return_value=MagicMock(status="queued")),
        ),
        patch("astra.telegram.handlers.natal.notify_natal_stage", new=AsyncMock()),
    ):
        await cb_natal_confirm(callback, state, session)

    subject_mock.assert_awaited_once()
    user_mock.assert_not_awaited()
    subject_arg = subject_mock.await_args.args[2]
    assert subject_arg.name == "Анжела"
    assert subject_arg.birth_date == date(1995, 6, 20)


def test_subject_keyboard_collapses_long_list() -> None:
    owner = uuid4()
    profiles = [_natal_profile(owner, birth_time=None) for _ in range(9)]
    keyboard = _subject_keyboard(profiles)
    callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    # 2 действия + 6 людей + «показать всех» + отмена
    pick_count = sum(1 for c in callbacks if c.startswith(CB_NATAL_SUBJECT_PICK_PREFIX))
    assert pick_count == 6
    assert CB_NATAL_SUBJECT_ALL in callbacks

    full = _subject_keyboard(profiles, show_all=True)
    full_cb = [b.callback_data for row in full.inline_keyboard for b in row]
    assert sum(1 for c in full_cb if c.startswith(CB_NATAL_SUBJECT_PICK_PREFIX)) == 9
    assert CB_NATAL_SUBJECT_ALL not in full_cb


def test_subject_keyboard_no_collapse_for_single_hidden() -> None:
    # 7 человек при лимите 6 — показываем всех без кнопки «Показать всех»
    owner = uuid4()
    keyboard = _subject_keyboard([_natal_profile(owner, birth_time=None) for _ in range(7)])
    callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    assert sum(1 for c in callbacks if c.startswith(CB_NATAL_SUBJECT_PICK_PREFIX)) == 7
    assert CB_NATAL_SUBJECT_ALL not in callbacks


@pytest.mark.anyio
async def test_subject_new_starts_name_collection() -> None:
    state = await _fsm_context()
    callback = _callback("natal:subject:new")

    await cb_natal_subject_new(callback, state)

    assert await state.get_state() == NatalStates.new_name.state
    data = await state.get_data()
    assert data["natal_subject_profile_id"] is None


@pytest.mark.anyio
async def test_new_name_advances_to_gender() -> None:
    state = await _fsm_context()
    await state.set_state(NatalStates.new_name)
    message = _message()
    message.text = "Тимур"
    session = AsyncMock()

    with patch(
        "astra.telegram.handlers.natal.users_crud.get_user_by_telegram_id",
        new=AsyncMock(return_value=_user(birth_time=None)),
    ):
        await collect_new_name(message, state, session)

    assert await state.get_state() == NatalStates.new_gender.state
    data = await state.get_data()
    assert data["natal_new_name"] == "Тимур"


@pytest.mark.anyio
async def test_complete_new_person_upserts_and_confirms() -> None:
    state = await _fsm_context()
    await state.set_state(NatalStates.new_birth_place_query)
    await state.update_data(
        natal_new_name="Тимур",
        natal_new_gender="мужчина",
        natal_new_birth_date="1994-03-10",
        natal_new_birth_time=None,
    )
    message = _message()
    session = AsyncMock()
    user = _user(birth_time=None)
    user.id = uuid4()
    saved_profile = _natal_profile(user.id, birth_time=None)
    saved_profile.label = "Тимур"

    with (
        patch(
            "astra.telegram.handlers.natal.users_crud.get_user_by_telegram_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "astra.telegram.handlers.natal.compatibility_crud.upsert_natal_profile",
            new=AsyncMock(return_value=saved_profile),
        ) as upsert_mock,
    ):
        await complete_natal_new_birth_place(
            message,
            state,
            session,
            place_display="Казань",
            place_id=uuid4(),
            timezone="Europe/Moscow",
            actor_telegram_id=42,
        )

    upsert_mock.assert_awaited_once()
    assert upsert_mock.await_args.kwargs["label"] == "Тимур"
    assert await state.get_state() == NatalStates.confirm.state
    data = await state.get_data()
    assert data["natal_subject_profile_id"] == str(saved_profile.id)
    # временные поля нового человека вычищены
    assert "natal_new_name" not in data
