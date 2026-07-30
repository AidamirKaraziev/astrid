"""Кнопка «🤷 Не знаю время» в разделе «Обо мне»: сбрасывает время рождения."""

from datetime import date, datetime, time
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from astra.telegram.button_texts import BTN_TIME_UNKNOWN, CB_PROFILE_TIME_UNKNOWN
from astra.telegram.handlers.menu import cb_birth_time_unknown, cb_edit_time
from astra.telegram.keyboards import profile_birth_time_keyboard


def test_keyboard_has_unknown_button() -> None:
    buttons = profile_birth_time_keyboard().inline_keyboard[0]
    assert [b.text for b in buttons] == [BTN_TIME_UNKNOWN]
    assert buttons[0].callback_data == CB_PROFILE_TIME_UNKNOWN


@pytest.mark.anyio
async def test_cb_edit_time_offers_unknown_button() -> None:
    callback = AsyncMock()
    callback.message = AsyncMock()
    state = AsyncMock()

    await cb_edit_time(callback, state)

    kwargs = callback.message.answer.await_args.kwargs
    assert kwargs["reply_markup"] == profile_birth_time_keyboard()
    assert "14:30" in callback.message.answer.await_args.args[0]
    callback.answer.assert_awaited_once()


@pytest.mark.anyio
async def test_unknown_clears_saved_birth_time() -> None:
    callback = AsyncMock()
    callback.from_user.id = 42
    callback.message = AsyncMock()
    state = AsyncMock()
    session = AsyncMock()

    profile = AsyncMock()
    profile.birth_time = datetime.combine(date(1990, 3, 15), time(14, 30))
    user = AsyncMock()
    user.profile = profile

    with (
        patch(
            "astra.telegram.handlers.menu._get_user",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch(
            "astra.telegram.handlers.menu.users_crud.clear_birth_time",
            new_callable=AsyncMock,
        ) as clear_birth_time,
    ):
        await cb_birth_time_unknown(callback, state, session)

    clear_birth_time.assert_awaited_once_with(session, profile)
    state.clear.assert_awaited_once()
    text = callback.message.answer.await_args.args[0]
    assert "Убрала время рождения" in text
    # Процент точности в этом ответе не показываем — только не пугать цифрой.
    assert "%" not in text
    callback.answer.assert_awaited()


@pytest.mark.anyio
async def test_unknown_without_saved_time_says_it_is_fine() -> None:
    callback = AsyncMock()
    callback.from_user.id = 42
    callback.message = AsyncMock()
    state = AsyncMock()
    session = AsyncMock()

    profile = AsyncMock()
    profile.birth_time = None
    user = AsyncMock()
    user.profile = profile

    with (
        patch(
            "astra.telegram.handlers.menu._get_user",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch(
            "astra.telegram.handlers.menu.users_crud.clear_birth_time",
            new_callable=AsyncMock,
        ),
    ):
        await cb_birth_time_unknown(callback, state, session)

    assert "обойдусь без времени" in callback.message.answer.await_args.args[0]


@pytest.mark.anyio
async def test_clear_birth_time_nulls_the_field() -> None:
    """update_profile игнорирует None — сброс идёт отдельной функцией."""
    from astra.users import crud as users_crud
    from astra.users.models import Profile

    profile = Profile(
        user_id=uuid4(),
        display_name="Анна",
        birth_date=date(1990, 3, 15),
        birth_time=datetime.combine(date(1990, 3, 15), time(14, 30)),
        birth_place="Москва",
        city="Москва",
        timezone="Europe/Moscow",
    )

    with (
        patch(
            "astra.users.crud._invalidate_today_predictions_if_astro_changed",
            new_callable=AsyncMock,
        ) as invalidate,
        patch("astra.users.crud._try_refresh_natal_chart", new_callable=AsyncMock),
    ):
        await users_crud.clear_birth_time(AsyncMock(), profile)

    assert profile.birth_time is None
    assert invalidate.await_args.args[2]["birth_time"] is not None


@pytest.mark.anyio
async def test_unknown_without_profile_asks_for_start() -> None:
    callback = AsyncMock()
    callback.from_user.id = 42
    callback.message = AsyncMock()

    with patch(
        "astra.telegram.handlers.menu._get_user",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await cb_birth_time_unknown(callback, AsyncMock(), AsyncMock())

    callback.message.answer.assert_not_awaited()
    callback.answer.assert_awaited_once_with("Сначала: /start", show_alert=True)
