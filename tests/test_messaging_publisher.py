from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from astra.messaging.publisher import _publish
from astra.messaging.schemas import TaskMessage, TaskType


@pytest.mark.asyncio
async def test_publish_always_sends_without_rabbitmq_enabled_flag() -> None:
    message = TaskMessage(type=TaskType.PREDICTION_SEND, user_id=uuid4())
    mock_exchange = AsyncMock()

    with (
        patch(
            "astra.messaging.publisher._get_channel",
            new=AsyncMock(return_value=(AsyncMock(), mock_exchange)),
        ),
        patch("astra.messaging.publisher.get_settings") as settings_mock,
    ):
        settings_mock.return_value = type("S", (), {"rabbitmq_url": "amqp://test"})()
        await _publish("prediction.send", message)

    mock_exchange.publish.assert_awaited_once()
