from unittest.mock import AsyncMock, patch

import pytest

from astra.telegram.handlers.menu import cb_edit_gender, cb_save_gender
from astra.telegram.keyboards import profile_gender_inline_keyboard
from astra.users.gender import GENDER_MALE


@pytest.mark.anyio
async def test_cb_edit_gender_shows_inline_keyboard() -> None:
    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.answer = AsyncMock()

    await cb_edit_gender(callback)

    callback.message.answer.assert_awaited_once()
    assert (
        callback.message.answer.await_args.kwargs["reply_markup"]
        == profile_gender_inline_keyboard()
    )
    callback.answer.assert_awaited_once()


@pytest.mark.anyio
async def test_cb_save_gender_updates_profile() -> None:
    callback = AsyncMock()
    callback.data = "profile:gender:male"
    callback.from_user.id = 42
    callback.message = AsyncMock()
    callback.answer = AsyncMock()

    profile = AsyncMock()
    profile.gender = None
    user = AsyncMock()
    user.profile = profile
    session = AsyncMock()

    with (
        patch(
            "astra.telegram.handlers.menu._get_user",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch(
            "astra.telegram.handlers.menu.users_crud.update_profile",
            new_callable=AsyncMock,
        ) as update_profile,
    ):
        await cb_save_gender(callback, session)

    update_profile.assert_awaited_once_with(session, profile, gender=GENDER_MALE)
    callback.message.answer.assert_awaited_once()
    assert "сохранён" in callback.message.answer.await_args.args[0].lower()
    callback.answer.assert_awaited_once()
