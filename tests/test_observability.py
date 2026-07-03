"""Тесты observability core: context, sanitization, correlation propagation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import structlog

from astra.core.observability import (
    Event,
    bound_context,
    configure_observability,
    ensure_correlation_id,
    get_correlation_id,
    get_logger,
    new_correlation_id,
)
from astra.core.observability.context import correlation_id_var, user_id_var
from astra.core.observability.processors import sanitize_pii
from astra.messaging.publisher import _publish
from astra.messaging.schemas import TaskMessage, TaskType


@pytest.fixture(autouse=True)
def _reset_observability() -> None:
    import astra.core.observability.logging as logging_module

    logging_module._CONFIGURED = False
    correlation_id_var.set(None)
    user_id_var.set(None)


@pytest.fixture
def observability_settings():
    return type(
        "S",
        (),
        {
            "log_level": "INFO",
            "log_format": "json",
            "sentry_service": "test",
            "otel_enabled": False,
        },
    )()


def test_new_correlation_id_has_prefix() -> None:
    cid = new_correlation_id("upd")
    assert cid.startswith("upd-")


def test_ensure_correlation_id_is_stable_in_context() -> None:
    with bound_context():
        first = ensure_correlation_id("task")
        second = ensure_correlation_id("task")
        assert first == second
        assert get_correlation_id() == first


def test_bound_context_resets_after_block() -> None:
    user_id = uuid4()
    with bound_context(correlation_id="cid-1", user_id=user_id):
        assert get_correlation_id() == "cid-1"
    assert get_correlation_id() is None


def test_sanitize_pii_masks_sensitive_keys() -> None:
    event_dict = {
        "event": "llm.response",
        "api_key": "secret-key",
        "user_id": str(uuid4()),
        "nested": {"prompt": "tell me everything"},
    }
    sanitized = sanitize_pii(None, "", event_dict)
    assert sanitized["api_key"] == "***"
    assert sanitized["nested"]["prompt"] == "***"
    assert sanitized["user_id"] != "***"


def test_structlog_json_includes_context(observability_settings, capsys) -> None:
    configure_observability(observability_settings)
    user_id = uuid4()
    with bound_context(correlation_id="cid-test", user_id=user_id):
        log = get_logger("test.observability")
        log.info(Event.TASK_PUBLISHED, task_type="prediction.generate")

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)
    assert payload["event"] == Event.TASK_PUBLISHED
    assert payload["correlation_id"] == "cid-test"
    assert payload["user_id"] == str(user_id)
    assert payload["service"] == "test"


def test_task_message_correlation_id_roundtrip() -> None:
    cid = new_correlation_id("task")
    msg = TaskMessage(
        type=TaskType.PREDICTION_GENERATE,
        user_id=uuid4(),
        correlation_id=cid,
    )
    restored = TaskMessage.model_validate_json(msg.model_dump_json())
    assert restored.correlation_id == cid


@pytest.mark.asyncio
async def test_publish_sets_correlation_header(observability_settings) -> None:
    configure_observability(observability_settings)
    user_id = uuid4()
    correlation_id = new_correlation_id("upd")

    with bound_context(correlation_id=correlation_id, user_id=user_id):
        message = TaskMessage(
            type=TaskType.PREDICTION_SEND,
            user_id=user_id,
            correlation_id=correlation_id,
        )
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
    published = mock_exchange.publish.await_args.args[0]
    assert published.headers["x-correlation-id"] == correlation_id


@pytest.mark.asyncio
async def test_worker_middleware_logs_lifecycle(observability_settings) -> None:
    from astra.core.observability.middleware.worker import run_task_with_observability

    configure_observability(observability_settings)
    task = TaskMessage(
        type=TaskType.PREDICTION_SEND,
        user_id=uuid4(),
        correlation_id="cid-worker",
    )
    message = AsyncMock()
    message.headers = {"x-correlation-id": "cid-worker"}
    message.message_id = "msg-1"
    message.routing_key = "prediction.send"

    with structlog.testing.capture_logs() as captured:
        await run_task_with_observability(message, task, AsyncMock())

    events = [entry["event"] for entry in captured]
    assert Event.TASK_RECEIVED in events
    assert Event.TASK_COMPLETED in events
