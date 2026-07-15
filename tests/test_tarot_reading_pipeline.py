"""Тесты worker-стадий раскладов: dispatch, resumability, фейл → уведомление."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from astra.messaging.schemas import TaskMessage, TaskType
from astra.tarot.enums import ReadingStatus
from astra.workers.handlers import (
    dispatch_task,
    handle_tarot_reading_generate,
    handle_tarot_reading_send,
)

_MODULE = "astra.workers.handlers"


def _task(task_type: TaskType, reading_id=None) -> TaskMessage:
    return TaskMessage(type=task_type, reading_id=reading_id)


class TestDispatch:
    async def test_routes_tarot_tasks(self):
        session = AsyncMock()
        with (
            patch(f"{_MODULE}.handle_tarot_reading_generate", AsyncMock()) as generate,
            patch(f"{_MODULE}.handle_tarot_reading_send", AsyncMock()) as send,
        ):
            await dispatch_task(session, _task(TaskType.TAROT_READING_GENERATE, uuid4()))
            await dispatch_task(session, _task(TaskType.TAROT_READING_SEND, uuid4()))
        generate.assert_awaited_once()
        send.assert_awaited_once()


class TestHandleGenerate:
    async def test_missing_reading_id_skipped(self):
        session = AsyncMock()
        with patch("astra.tarot.models.get_reading", AsyncMock()) as get_reading:
            await handle_tarot_reading_generate(session, _task(TaskType.TAROT_READING_GENERATE))
        get_reading.assert_not_awaited()

    async def test_success_commits_then_publishes_send(self):
        session = AsyncMock()
        reading = MagicMock(
            id=uuid4(), user_id=uuid4(), interpretation=None, status=ReadingStatus.PENDING,
        )
        with (
            patch("astra.tarot.models.get_reading", AsyncMock(return_value=reading)),
            patch(f"{_MODULE}.users_crud.get_user_by_id", AsyncMock(return_value=MagicMock())),
            patch(f"{_MODULE}.send_chat_action_typing", AsyncMock()),
            patch(
                f"{_MODULE}.generate_reading_interpretation",
                AsyncMock(return_value=reading),
            ),
            patch(f"{_MODULE}.publish_tarot_reading_send", AsyncMock()) as publish,
        ):
            await handle_tarot_reading_generate(
                session, _task(TaskType.TAROT_READING_GENERATE, reading.id),
            )
        session.commit.assert_awaited_once()
        publish.assert_awaited_once_with(reading.id)

    async def test_resumability_skips_llm_when_text_ready(self):
        session = AsyncMock()
        reading = MagicMock(
            id=uuid4(), interpretation="готово", status=ReadingStatus.TEXT_READY,
        )
        with (
            patch("astra.tarot.models.get_reading", AsyncMock(return_value=reading)),
            patch(f"{_MODULE}.generate_reading_interpretation", AsyncMock()) as generate,
            patch(f"{_MODULE}.publish_tarot_reading_send", AsyncMock()) as publish,
        ):
            await handle_tarot_reading_generate(
                session, _task(TaskType.TAROT_READING_GENERATE, reading.id),
            )
        generate.assert_not_awaited()
        publish.assert_awaited_once_with(reading.id)

    async def test_failure_notifies_user(self):
        session = AsyncMock()
        reading = MagicMock(
            id=uuid4(), user_id=uuid4(), interpretation=None, status=ReadingStatus.PENDING,
        )
        with (
            patch("astra.tarot.models.get_reading", AsyncMock(return_value=reading)),
            patch(f"{_MODULE}.users_crud.get_user_by_id", AsyncMock(return_value=MagicMock())),
            patch(f"{_MODULE}.send_chat_action_typing", AsyncMock()),
            patch(f"{_MODULE}.generate_reading_interpretation", AsyncMock(return_value=None)),
            patch(f"{_MODULE}.notify_reading_failed", AsyncMock()) as notify,
            patch(f"{_MODULE}.publish_tarot_reading_send", AsyncMock()) as publish,
        ):
            await handle_tarot_reading_generate(
                session, _task(TaskType.TAROT_READING_GENERATE, reading.id),
            )
        session.commit.assert_awaited_once()  # failed-статус фиксируется
        notify.assert_awaited_once()
        publish.assert_not_awaited()


class TestHandleSend:
    async def test_commits_only_when_sent(self):
        session = AsyncMock()
        with patch(f"{_MODULE}.deliver_reading", AsyncMock(return_value=True)):
            await handle_tarot_reading_send(session, _task(TaskType.TAROT_READING_SEND, uuid4()))
        session.commit.assert_awaited_once()

        session = AsyncMock()
        with patch(f"{_MODULE}.deliver_reading", AsyncMock(return_value=False)):
            await handle_tarot_reading_send(session, _task(TaskType.TAROT_READING_SEND, uuid4()))
        session.commit.assert_not_awaited()
