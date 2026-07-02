from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from astra.messaging.schemas import TaskMessage, TaskType
from astra.workers import handlers


@pytest.mark.asyncio
async def test_handle_natal_chart_generate_publishes_daily_context() -> None:
    user_id = uuid4()
    target = date(2026, 7, 2)
    user = MagicMock()
    user.id = user_id
    user.telegram_id = 1001
    user.profile = MagicMock(timezone="Europe/Moscow")
    session = AsyncMock()
    task = TaskMessage(
        type=TaskType.NATAL_CHART_GENERATE,
        user_id=user_id,
        prediction_date=target,
    )

    with (
        patch(
            "astra.workers.handlers.users_crud.get_user_by_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "astra.workers.handlers.compute_and_store_natal_chart",
            new=AsyncMock(),
        ),
        patch(
            "astra.workers.handlers.notify_prediction_stage",
            new=AsyncMock(),
        ) as notify_mock,
        patch(
            "astra.workers.handlers.publish_daily_context_build",
            new=AsyncMock(),
        ) as publish_mock,
    ):
        await handlers.handle_natal_chart_generate(session, task)

    session.commit.assert_awaited_once()
    notify_mock.assert_awaited_once()
    publish_mock.assert_awaited_once_with(user_id, target)


@pytest.mark.asyncio
async def test_handle_daily_context_build_publishes_prediction_generate() -> None:
    user_id = uuid4()
    target = date(2026, 7, 2)
    user = MagicMock()
    user.id = user_id
    user.telegram_id = 1001
    user.profile = MagicMock(timezone="Europe/Moscow")
    session = AsyncMock()
    task = TaskMessage(
        type=TaskType.DAILY_CONTEXT_BUILD,
        user_id=user_id,
        prediction_date=target,
    )

    with (
        patch(
            "astra.workers.handlers.users_crud.get_user_by_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "astra.workers.handlers.build_and_store_daily_context",
            new=AsyncMock(),
        ),
        patch(
            "astra.workers.handlers.notify_prediction_stage",
            new=AsyncMock(),
        ),
        patch(
            "astra.workers.handlers.publish_prediction_generate",
            new=AsyncMock(),
        ) as publish_mock,
    ):
        await handlers.handle_daily_context_build(session, task)

    publish_mock.assert_awaited_once_with(user_id, target)
