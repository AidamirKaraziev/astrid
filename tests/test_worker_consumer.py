from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from astra.core.observability import Event
from astra.messaging.schemas import TaskMessage, TaskType
from astra.workers import handlers
from astra.workers.consumer import MAX_TASK_RETRIES, _process_message, check_daily_provider_configured
from astra.workers.telegram_send import BotBlockedError


def _cfg(*, enabled: bool, api_key: str) -> SimpleNamespace:
    return SimpleNamespace(deepseek_enabled=enabled, deepseek_api_key=api_key)


def test_warns_when_daily_provider_unconfigured() -> None:
    with patch("astra.workers.consumer.log") as log:
        check_daily_provider_configured(_cfg(enabled=False, api_key=""))

    log.warning.assert_called_once()
    assert log.warning.call_args.args[0] == Event.LLM_DAILY_PROVIDER_UNCONFIGURED


def test_silent_when_daily_provider_configured() -> None:
    with patch("astra.workers.consumer.log") as log:
        check_daily_provider_configured(_cfg(enabled=True, api_key="sk-x"))

    log.warning.assert_not_called()


# --- сбой задачи не крутится вечно ---

_MODULE = "astra.workers.consumer"
_ROUTING_KEY = "prediction.send"


class FakeMessage:
    """Как IncomingMessage: ack при чистом выходе из process(), reject при исключении."""

    def __init__(self, task: TaskMessage) -> None:
        self.body = task.model_dump_json().encode()
        self.routing_key = _ROUTING_KEY
        self.message_id = None
        self.headers: dict[str, str] = {}
        self.acked = 0
        self.rejected: list[bool] = []

    @asynccontextmanager
    async def process(self, requeue: bool = True):
        try:
            yield self
        except BaseException:
            self.rejected.append(requeue)
            raise
        self.acked += 1


class FakeBroker:
    """Публикатор-заглушка: копии запоминает, как RabbitMQ вернул бы их консьюмеру."""

    def __init__(self, *, down: bool = False) -> None:
        self.published: list[tuple[str, TaskMessage]] = []
        self.down = down

    async def republish_task(self, routing_key: str, task: TaskMessage) -> TaskMessage:
        if self.down:
            raise ConnectionError("rabbit down")
        retried = task.model_copy(update={"retry": task.retry + 1})
        self.published.append((routing_key, retried))
        return retried


def _factory():
    @asynccontextmanager
    async def factory():
        yield AsyncMock()

    return factory


async def _drain(dispatch: AsyncMock, broker: FakeBroker, dead: AsyncMock) -> list[FakeMessage]:
    """Гоняет задачу через консьюмер, пока копии не кончатся (предохранитель: 50 доставок)."""
    queue = [TaskMessage(type=TaskType.PREDICTION_SEND, user_id=uuid4())]
    seen: list[FakeMessage] = []
    taken = 0
    with (
        patch(f"{_MODULE}.get_session_factory", return_value=_factory()),
        patch(f"{_MODULE}.dispatch_task", dispatch),
        patch(f"{_MODULE}.republish_task", broker.republish_task),
        patch(f"{_MODULE}.handle_task_dead", dead),
    ):
        while queue and len(seen) < 50:
            message = FakeMessage(queue.pop(0))
            seen.append(message)
            await _process_message(message)  # type: ignore[arg-type]
            queue.extend(task for _, task in broker.published[taken:])
            taken = len(broker.published)
    return seen


async def test_deterministic_failure_gives_five_republishes_and_one_dead() -> None:
    broker = FakeBroker()
    dead = AsyncMock()

    seen = await _drain(AsyncMock(side_effect=RuntimeError("boom")), broker, dead)

    assert [t.retry for _, t in broker.published] == [1, 2, 3, 4, 5]
    assert {key for key, _ in broker.published} == {_ROUTING_KEY}
    assert len(seen) == MAX_TASK_RETRIES + 1
    assert all(m.acked == 1 and m.rejected == [] for m in seen)
    dead.assert_awaited_once()
    assert dead.await_args.args[1].retry == MAX_TASK_RETRIES


async def test_success_acks_without_publishing() -> None:
    broker = FakeBroker()
    dead = AsyncMock()

    seen = await _drain(AsyncMock(), broker, dead)

    assert len(seen) == 1 and seen[0].acked == 1 and seen[0].rejected == []
    assert broker.published == []
    dead.assert_not_awaited()


async def test_bot_blocked_acks_without_retry_or_dead() -> None:
    broker = FakeBroker()
    dead = AsyncMock()
    with patch(f"{_MODULE}.users_crud.mark_bot_blocked", AsyncMock()) as mark:
        seen = await _drain(AsyncMock(side_effect=BotBlockedError(42)), broker, dead)

    assert len(seen) == 1 and seen[0].acked == 1
    assert broker.published == []
    mark.assert_awaited_once()
    dead.assert_not_awaited()


async def test_failed_republish_requeues_original() -> None:
    """Rabbit лёг при повторной публикации: старое поведение, сообщение не теряется."""
    broker = FakeBroker(down=True)
    dead = AsyncMock()
    message = FakeMessage(TaskMessage(type=TaskType.PREDICTION_SEND, user_id=uuid4()))
    with (
        patch(f"{_MODULE}.get_session_factory", return_value=_factory()),
        patch(f"{_MODULE}.dispatch_task", AsyncMock(side_effect=RuntimeError("boom"))),
        patch(f"{_MODULE}.republish_task", broker.republish_task),
        patch(f"{_MODULE}.handle_task_dead", dead),
        pytest.raises(RuntimeError, match="boom"),
    ):
        await _process_message(message)  # type: ignore[arg-type]

    assert message.acked == 0 and message.rejected == [True]
    dead.assert_not_awaited()


async def test_exhausted_task_logs_task_dead_event_once() -> None:
    broker = FakeBroker()
    with patch(f"{_MODULE}.log") as log:
        await _drain(AsyncMock(side_effect=RuntimeError("boom")), broker, AsyncMock())

    dead_calls = [c for c in log.error.call_args_list if c.args and c.args[0] == Event.TASK_DEAD]
    assert len(dead_calls) == 1
    assert dead_calls[0].kwargs["retry"] == MAX_TASK_RETRIES


async def test_human_gets_one_failure_message_through_real_dead_handler() -> None:
    """Обратный контроль: пять повторов не шлют по сообщению каждый — сообщает только последний."""
    broker = FakeBroker()
    with patch("astra.workers.handlers._dead_prediction", AsyncMock()) as told:
        seen = await _drain(
            AsyncMock(side_effect=RuntimeError("boom")),
            broker,
            handlers.handle_task_dead,
        )

    assert len(seen) == MAX_TASK_RETRIES + 1
    told.assert_awaited_once()


async def test_last_allowed_retry_still_republishes() -> None:
    broker = FakeBroker()
    dead = AsyncMock()
    task = TaskMessage(type=TaskType.PREDICTION_SEND, user_id=uuid4(), retry=MAX_TASK_RETRIES - 1)
    message = FakeMessage(task)
    with (
        patch(f"{_MODULE}.get_session_factory", return_value=_factory()),
        patch(f"{_MODULE}.dispatch_task", AsyncMock(side_effect=RuntimeError("boom"))),
        patch(f"{_MODULE}.republish_task", broker.republish_task),
        patch(f"{_MODULE}.handle_task_dead", dead),
    ):
        await _process_message(message)  # type: ignore[arg-type]

    assert [t.retry for _, t in broker.published] == [MAX_TASK_RETRIES]
    assert message.acked == 1
    dead.assert_not_awaited()
