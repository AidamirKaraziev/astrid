"""Правка места рождения в «Обо мне» идёт через выбор города из справочника.

Раньше название сохранялось свободным текстом, а координаты подбирались
молча по первому совпадению: человек писал «Иваново» и не знал, какое из
двух десятков лягло в его карту.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from astra.telegram.handlers.menu import cb_edit_place, complete_profile_birth_place
from astra.telegram.handlers.places import SEARCH_HINT, _apply_place_selection
from astra.telegram.keyboard_policy import is_fsm_keyboard_suppressed
from astra.telegram.states import ProfileStates
from astra.users.models import Profile


async def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=2, user_id=3)
    return FSMContext(storage=storage, key=key)


def _user(*, gender: str | None = "женщина", notification_place_id=None) -> MagicMock:
    user = MagicMock()
    user.profile = Profile(
        user_id=uuid4(),
        display_name="Анна",
        gender=gender,
        birth_date=date(1990, 3, 15),
        birth_place="Москва",
        notification_place_id=notification_place_id,
        city="Москва",
        timezone="Europe/Moscow",
    )
    return user


def _place() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        display_name="Иваново, Тверская область",
        timezone="Europe/Moscow",
    )


@pytest.mark.anyio
async def test_edit_place_starts_city_search_in_her_gender() -> None:
    callback = AsyncMock()
    callback.from_user.id = 42
    callback.message = AsyncMock()
    state = await _fsm_context()

    with patch(
        "astra.telegram.handlers.menu._get_user",
        new=AsyncMock(return_value=_user()),
    ):
        await cb_edit_place(callback, state, AsyncMock())

    assert await state.get_state() == ProfileStates.edit_birth_place_query.state
    text = callback.message.answer.await_args.args[0]
    assert "Где ты родилась?" in text
    assert SEARCH_HINT in text
    callback.answer.assert_awaited_once()


@pytest.mark.anyio
async def test_edit_place_without_gender_avoids_gendered_form() -> None:
    callback = AsyncMock()
    callback.from_user.id = 42
    callback.message = AsyncMock()

    with patch(
        "astra.telegram.handlers.menu._get_user",
        new=AsyncMock(return_value=_user(gender=None)),
    ):
        await cb_edit_place(callback, await _fsm_context(), AsyncMock())

    assert "Где твоё место рождения?" in callback.message.answer.await_args.args[0]


@pytest.mark.anyio
async def test_picked_place_lands_in_profile_with_its_id() -> None:
    state = await _fsm_context()
    await state.set_state(ProfileStates.edit_birth_place_query)
    message = AsyncMock()
    place = _place()

    with (
        patch(
            "astra.telegram.handlers.menu._get_user",
            new=AsyncMock(return_value=_user()),
        ),
        patch(
            "astra.telegram.handlers.menu.users_crud.update_profile",
            new_callable=AsyncMock,
        ) as update_profile,
        patch("astra.telegram.handlers.menu._send_portrait", new_callable=AsyncMock) as portrait,
    ):
        await complete_profile_birth_place(
            message,
            state,
            AsyncMock(),
            place=place,
            actor_telegram_id=42,
        )

    fields = update_profile.await_args.kwargs
    assert fields["birth_place_id"] == place.id
    assert fields["birth_place"] == place.display_name
    # Города уведомлений у человека нет — рассылка идёт по месту рождения.
    assert fields["city"] == place.display_name
    assert fields["timezone"] == place.timezone

    # Человек должен увидеть, какое именно место легло в профиль.
    assert place.display_name in message.answer.await_args.args[0]
    assert await state.get_state() is None
    portrait.assert_awaited_once()


@pytest.mark.anyio
async def test_own_notification_city_survives_birth_place_edit() -> None:
    state = await _fsm_context()
    await state.set_state(ProfileStates.edit_birth_place_query)

    with (
        patch(
            "astra.telegram.handlers.menu._get_user",
            new=AsyncMock(return_value=_user(notification_place_id=uuid4())),
        ),
        patch(
            "astra.telegram.handlers.menu.users_crud.update_profile",
            new_callable=AsyncMock,
        ) as update_profile,
        patch("astra.telegram.handlers.menu._send_portrait", new_callable=AsyncMock),
    ):
        await complete_profile_birth_place(
            AsyncMock(),
            state,
            AsyncMock(),
            place=_place(),
            actor_telegram_id=42,
        )

    fields = update_profile.await_args.kwargs
    assert "city" not in fields
    assert "timezone" not in fields


@pytest.mark.anyio
async def test_place_pick_from_profile_goes_to_profile_save() -> None:
    """Выбор города в этом состоянии не должен уехать в чужой сценарий."""
    state = await _fsm_context()
    await state.set_state(ProfileStates.edit_birth_place_query)
    place = _place()

    with (
        patch(
            "astra.telegram.handlers.places.get_place_read",
            new=AsyncMock(return_value=place),
        ),
        patch(
            "astra.telegram.handlers.menu.complete_profile_birth_place",
            new_callable=AsyncMock,
        ) as complete,
    ):
        await _apply_place_selection(
            AsyncMock(),
            state,
            AsyncMock(),
            place.id,
            actor_telegram_id=42,
        )

    complete.assert_awaited_once()
    assert complete.await_args.kwargs["place"] is place


def test_main_menu_is_hidden_while_the_city_is_being_picked() -> None:
    assert is_fsm_keyboard_suppressed(ProfileStates.edit_birth_place_query.state)


@pytest.mark.anyio
async def test_place_chosen_from_catalog_is_not_re_searched_by_name() -> None:
    """id из справочника — окончательный: поиск по названию нашёл бы тёзку."""
    from astra.users import crud as users_crud

    profile = MagicMock()
    place_id = uuid4()

    with (
        patch("astra.users.crud._resolve_birth_place_id", new_callable=AsyncMock) as resolve,
        patch(
            "astra.users.crud._invalidate_today_predictions_if_astro_changed",
            new_callable=AsyncMock,
        ),
        patch("astra.users.crud._try_refresh_natal_chart", new_callable=AsyncMock),
    ):
        await users_crud.update_profile(
            AsyncMock(),
            profile,
            birth_place_id=place_id,
            birth_place="Иваново, Тверская область",
        )

    resolve.assert_not_awaited()
    assert profile.birth_place_id == place_id
