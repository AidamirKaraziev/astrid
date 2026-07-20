"""403 от Bot API = пользователь заблокировал бота: пометка, ack без requeue, /start."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from astra.users import crud as users_crud
from astra.workers.consumer import _process_message
from astra.workers.telegram_send import BotBlockedError, _raise_for_status


class TestRaiseForStatus:
    def test_403_raises_bot_blocked(self):
        response = MagicMock(status_code=403)
        with pytest.raises(BotBlockedError) as exc_info:
            _raise_for_status(response, 42)
        assert exc_info.value.telegram_id == 42
        response.raise_for_status.assert_not_called()

    def test_other_errors_raise_as_usual(self):
        response = MagicMock(status_code=500)
        _raise_for_status(response, 42)
        response.raise_for_status.assert_called_once()


class TestMarkBotBlocked:
    async def test_sets_flag_once(self):
        user = MagicMock(id=uuid4(), bot_blocked_at=None)
        session = AsyncMock()
        with patch.object(users_crud, "get_user_by_telegram_id", AsyncMock(return_value=user)):
            await users_crud.mark_bot_blocked(session, 42)
        assert user.bot_blocked_at is not None
        session.flush.assert_awaited_once()

    async def test_already_blocked_is_noop(self):
        user = MagicMock(id=uuid4(), bot_blocked_at=MagicMock())
        session = AsyncMock()
        with patch.object(users_crud, "get_user_by_telegram_id", AsyncMock(return_value=user)):
            await users_crud.mark_bot_blocked(session, 42)
        session.flush.assert_not_awaited()

    async def test_unknown_user_is_noop(self):
        session = AsyncMock()
        with patch.object(users_crud, "get_user_by_telegram_id", AsyncMock(return_value=None)):
            await users_crud.mark_bot_blocked(session, 42)
        session.flush.assert_not_awaited()


class TestClearBotBlocked:
    async def test_clears_flag(self):
        user = MagicMock(id=uuid4(), telegram_id=42, bot_blocked_at=MagicMock())
        session = AsyncMock()
        await users_crud.clear_bot_blocked(session, user)
        assert user.bot_blocked_at is None
        session.flush.assert_awaited_once()

    async def test_not_blocked_is_noop(self):
        user = MagicMock(id=uuid4(), telegram_id=42, bot_blocked_at=None)
        session = AsyncMock()
        await users_crud.clear_bot_blocked(session, user)
        session.flush.assert_not_awaited()


class TestConsumerHandlesBlocked:
    def _message(self) -> MagicMock:
        message = MagicMock()

        @asynccontextmanager
        async def process(requeue: bool = True):
            yield

        message.process = process
        return message

    def _session_factory(self, session: AsyncMock):
        @asynccontextmanager
        async def factory():
            yield session

        return factory

    async def test_bot_blocked_marks_user_and_acks(self):
        """BotBlockedError не долетает до aio_pika — задача подтверждается."""
        session = AsyncMock()
        _MODULE = "astra.workers.consumer"

        async def run_directly(message, task, fn):
            await fn()

        with (
            patch(f"{_MODULE}.parse_task", MagicMock(return_value=MagicMock())),
            patch(f"{_MODULE}.get_session_factory", return_value=self._session_factory(session)),
            patch(f"{_MODULE}.run_task_with_observability", side_effect=run_directly),
            patch(f"{_MODULE}.dispatch_task", AsyncMock(side_effect=BotBlockedError(42))),
            patch(f"{_MODULE}.users_crud.mark_bot_blocked", AsyncMock()) as mark,
        ):
            await _process_message(self._message())  # не должно бросить
        mark.assert_awaited_once()
        assert mark.await_args.args[1] == 42
        session.rollback.assert_awaited_once()
        session.commit.assert_awaited_once()  # коммит пометки

    async def test_other_errors_still_propagate(self):
        session = AsyncMock()
        _MODULE = "astra.workers.consumer"

        async def run_directly(message, task, fn):
            await fn()

        with (
            patch(f"{_MODULE}.parse_task", MagicMock(return_value=MagicMock())),
            patch(f"{_MODULE}.get_session_factory", return_value=self._session_factory(session)),
            patch(f"{_MODULE}.run_task_with_observability", side_effect=run_directly),
            patch(f"{_MODULE}.dispatch_task", AsyncMock(side_effect=RuntimeError("llm down"))),
        ):
            with pytest.raises(RuntimeError):
                await _process_message(self._message())
