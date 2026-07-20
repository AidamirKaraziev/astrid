from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from astra.telegram.handlers.start import cmd_start


@pytest.mark.anyio
async def test_cmd_start_prompts_gender_for_legacy_profile() -> None:
    message = AsyncMock()
    message.from_user.id = 42
    message.from_user.username = "aid"
    message.from_user.language_code = "ru"
    message.answer = AsyncMock()

    command = AsyncMock()
    command.args = None

    state = AsyncMock()
    state.clear = AsyncMock()

    session = AsyncMock()
    user = SimpleNamespace(
        id=1,
        onboarding_completed=True,
        bot_blocked_at=None,
        profile=SimpleNamespace(gender=None),
    )

    with (
        patch(
            "astra.telegram.handlers.start.users_crud.get_user_by_telegram_id",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch(
            "astra.telegram.handlers.start.sync_user_from_telegram",
            new_callable=AsyncMock,
        ),
        patch(
            "astra.telegram.handlers.start.register_daily_activity",
            new_callable=AsyncMock,
        ),
    ):
        await cmd_start(message, command, state, session)

    assert message.answer.await_count == 2
    assert "Главное меню" in message.answer.await_args_list[0].args[0]
    assert "укажи свой пол" in message.answer.await_args_list[1].args[0].lower()


@pytest.mark.anyio
async def test_cmd_start_skips_gender_prompt_when_set() -> None:
    message = AsyncMock()
    message.from_user.id = 42
    message.from_user.username = "aid"
    message.from_user.language_code = "ru"
    message.answer = AsyncMock()

    command = AsyncMock()
    command.args = None

    state = AsyncMock()
    state.clear = AsyncMock()

    session = AsyncMock()
    user = SimpleNamespace(
        id=1,
        onboarding_completed=True,
        bot_blocked_at=None,
        profile=SimpleNamespace(gender="мужчина"),
    )

    with (
        patch(
            "astra.telegram.handlers.start.users_crud.get_user_by_telegram_id",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch(
            "astra.telegram.handlers.start.sync_user_from_telegram",
            new_callable=AsyncMock,
        ),
        patch(
            "astra.telegram.handlers.start.register_daily_activity",
            new_callable=AsyncMock,
        ),
    ):
        await cmd_start(message, command, state, session)

    message.answer.assert_awaited_once()
