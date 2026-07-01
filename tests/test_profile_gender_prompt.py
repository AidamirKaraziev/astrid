from unittest.mock import AsyncMock

import pytest

from astra.telegram.profile_gender_prompt import (
    GENDER_PROMPT_TEXT,
    profile_needs_gender,
    prompt_gender_if_missing,
)
from astra.telegram.keyboards import profile_gender_inline_keyboard
from astra.users.gender import GENDER_MALE


def test_profile_needs_gender() -> None:
    from types import SimpleNamespace

    assert profile_needs_gender(SimpleNamespace(gender=GENDER_MALE)) is False
    assert profile_needs_gender(SimpleNamespace(gender=None)) is True
    assert profile_needs_gender(None) is False


@pytest.mark.anyio
async def test_prompt_gender_if_missing_when_set() -> None:
    from types import SimpleNamespace

    message = AsyncMock()
    ok = await prompt_gender_if_missing(message, SimpleNamespace(gender=GENDER_MALE))
    assert ok is True
    message.answer.assert_not_awaited()


@pytest.mark.anyio
async def test_prompt_gender_if_missing_when_empty() -> None:
    from types import SimpleNamespace

    message = AsyncMock()
    ok = await prompt_gender_if_missing(message, SimpleNamespace(gender=None))
    assert ok is False
    message.answer.assert_awaited_once_with(
        GENDER_PROMPT_TEXT,
        reply_markup=profile_gender_inline_keyboard(),
    )
