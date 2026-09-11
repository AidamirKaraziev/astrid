from datetime import date
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from astra.telegram.progress.api import edit_html_message
from astra.telegram.progress.messages import (
    compatibility_stage_text,
    prediction_stage_text,
)
from astra.telegram.progress.notifier import (
    advance_progress,
    clear_progress,
    notify_compatibility_stage,
    notify_prediction_stage,
)
from astra.telegram.progress.stages import (
    CompatibilityStage,
    PredictionStage,
    compatibility_job_key,
    prediction_job_key,
)
from astra.telegram.progress.store import (
    clear_progress_message_id,
    get_progress_message_id,
    progress_redis_key,
    set_progress_message_id,
)


def test_prediction_job_key() -> None:
    assert prediction_job_key(date(2026, 7, 2)) == "prediction:2026-07-02"


def test_compatibility_job_key() -> None:
    report_id = uuid4()
    assert compatibility_job_key(report_id) == f"compatibility:{report_id}"


def test_prediction_stage_texts_non_empty() -> None:
    for stage in PredictionStage:
        text = prediction_stage_text(stage)
        assert text.strip()
        assert "✨" in text or "🌙" in text


def test_compatibility_stage_texts_non_empty() -> None:
    for stage in CompatibilityStage:
        text = compatibility_stage_text(stage)
        assert text.strip()


@pytest.mark.asyncio
async def test_progress_store_roundtrip() -> None:
    user_id = uuid4()
    job_key = prediction_job_key(date(2026, 7, 2))
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=None)
    mock_client.set = AsyncMock()
    mock_client.delete = AsyncMock()
    mock_client.aclose = AsyncMock()

    with patch("astra.telegram.progress.store._redis", return_value=mock_client):
        assert await get_progress_message_id(user_id, job_key) is None
        await set_progress_message_id(user_id, job_key, 42)
        mock_client.set.assert_called_once()

    mock_client.get = AsyncMock(return_value="42")
    with patch("astra.telegram.progress.store._redis", return_value=mock_client):
        assert await get_progress_message_id(user_id, job_key) == 42

    mock_client.get = AsyncMock(return_value="42")
    with patch("astra.telegram.progress.store._redis", return_value=mock_client):
        assert await clear_progress_message_id(user_id, job_key) == 42
        mock_client.delete.assert_called_once_with(progress_redis_key(user_id, job_key))


@pytest.mark.asyncio
async def test_advance_progress_edits_existing_message() -> None:
    """Стадия переписывает висящее сообщение: без мигания и рывка чата наверх."""
    user_id = uuid4()
    chat_id = 1001
    job_key = "prediction:2026-07-02"

    with (
        patch(
            "astra.telegram.progress.notifier.get_progress_message_id",
            new=AsyncMock(return_value=10),
        ),
        patch(
            "astra.telegram.progress.notifier.edit_html_message",
            new=AsyncMock(return_value=True),
        ) as edit_mock,
        patch(
            "astra.telegram.progress.notifier.send_chat_action_typing",
            new=AsyncMock(),
        ) as typing_mock,
        patch(
            "astra.telegram.progress.notifier.send_html_message",
            new=AsyncMock(return_value=11),
        ) as send_mock,
        patch(
            "astra.telegram.progress.notifier.set_progress_message_id",
            new=AsyncMock(),
        ) as save_mock,
    ):
        message_id = await advance_progress(
            chat_id,
            user_id,
            job_key,
            "Тестовый прогресс ✨",
            with_typing=True,
        )

    assert message_id == 10
    edit_mock.assert_awaited_once_with(chat_id, 10, "Тестовый прогресс ✨", settings=None)
    send_mock.assert_not_awaited()
    typing_mock.assert_not_awaited()
    save_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_advance_progress_sends_new_when_edit_impossible() -> None:
    """Человек удалил сообщение прогресса — стадия заводит новое, а не молчит."""
    user_id = uuid4()
    chat_id = 1001
    job_key = "prediction:2026-07-02"

    with (
        patch(
            "astra.telegram.progress.notifier.get_progress_message_id",
            new=AsyncMock(return_value=10),
        ),
        patch(
            "astra.telegram.progress.notifier.edit_html_message",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "astra.telegram.progress.notifier.clear_progress_message_id",
            new=AsyncMock(return_value=10),
        ) as forget_mock,
        patch(
            "astra.telegram.progress.notifier.send_chat_action_typing",
            new=AsyncMock(),
        ) as typing_mock,
        patch(
            "astra.telegram.progress.notifier.send_html_message",
            new=AsyncMock(return_value=11),
        ) as send_mock,
        patch(
            "astra.telegram.progress.notifier.set_progress_message_id",
            new=AsyncMock(),
        ) as save_mock,
    ):
        message_id = await advance_progress(
            chat_id,
            user_id,
            job_key,
            "Тестовый прогресс ✨",
            with_typing=True,
        )

    assert message_id == 11
    forget_mock.assert_awaited_once_with(user_id, job_key)
    typing_mock.assert_awaited_once()
    send_mock.assert_awaited_once()
    save_mock.assert_awaited_once_with(user_id, job_key, 11)


@pytest.mark.asyncio
async def test_first_stage_sends_message_without_editing() -> None:
    """Первая стадия: править нечего, шлём сообщение и запоминаем его."""
    user_id = uuid4()
    chat_id = 1001
    job_key = "prediction:2026-07-02"

    with (
        patch(
            "astra.telegram.progress.notifier.get_progress_message_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "astra.telegram.progress.notifier.edit_html_message",
            new=AsyncMock(),
        ) as edit_mock,
        patch(
            "astra.telegram.progress.notifier.send_chat_action_typing",
            new=AsyncMock(),
        ),
        patch(
            "astra.telegram.progress.notifier.send_html_message",
            new=AsyncMock(return_value=5),
        ) as send_mock,
        patch(
            "astra.telegram.progress.notifier.set_progress_message_id",
            new=AsyncMock(),
        ) as save_mock,
    ):
        message_id = await advance_progress(chat_id, user_id, job_key, "Старт ✨", with_typing=False)

    assert message_id == 5
    edit_mock.assert_not_awaited()
    send_mock.assert_awaited_once()
    save_mock.assert_awaited_once_with(user_id, job_key, 5)


@pytest.mark.asyncio
async def test_notify_prediction_stage_uses_stage_text() -> None:
    user_id = uuid4()
    target = date(2026, 7, 2)

    with patch(
        "astra.telegram.progress.notifier.advance_progress",
        new=AsyncMock(return_value=7),
    ) as advance_mock:
        result = await notify_prediction_stage(
            1001,
            user_id,
            target,
            PredictionStage.CONTEXT_DONE,
        )

    assert result == 7
    advance_mock.assert_awaited_once()
    args = advance_mock.await_args
    assert args.args[2] == prediction_job_key(target)
    assert args.args[3] == prediction_stage_text(PredictionStage.CONTEXT_DONE)


@pytest.mark.asyncio
async def test_notify_compatibility_stage_uses_stage_text() -> None:
    user_id = uuid4()
    report_id = uuid4()

    with patch(
        "astra.telegram.progress.notifier.advance_progress",
        new=AsyncMock(return_value=9),
    ) as advance_mock:
        result = await notify_compatibility_stage(
            1001,
            user_id,
            report_id,
            CompatibilityStage.SYNASTRY_DONE,
        )

    assert result == 9
    advance_mock.assert_awaited_once()
    args = advance_mock.await_args
    assert args.args[2] == compatibility_job_key(report_id)
    assert args.args[3] == compatibility_stage_text(CompatibilityStage.SYNASTRY_DONE)


@pytest.mark.asyncio
async def test_clear_progress_deletes_message_and_key() -> None:
    user_id = uuid4()
    chat_id = 1001
    job_key = "prediction:2026-07-02"

    with (
        patch(
            "astra.telegram.progress.notifier.clear_progress_message_id",
            new=AsyncMock(return_value=15),
        ),
        patch(
            "astra.telegram.progress.notifier.delete_message",
            new=AsyncMock(return_value=True),
        ) as delete_mock,
    ):
        await clear_progress(chat_id, user_id, job_key)

    delete_mock.assert_awaited_once_with(chat_id, 15, settings=None)


class _FakeHttpClient:
    """httpx.AsyncClient, который отвечает заранее заданным ответом."""

    def __init__(self, response: httpx.Response | Exception) -> None:
        self._response = response

    async def __aenter__(self) -> "_FakeHttpClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def post(self, *args: Any, **kwargs: Any) -> httpx.Response:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _with_http(response: httpx.Response | Exception):
    if isinstance(response, httpx.Response):
        # Без привязанного запроса httpx не даёт вызвать raise_for_status.
        response.request = httpx.Request("POST", "https://api.telegram.org/editMessageText")
    return patch(
        "astra.telegram.progress.api.httpx.AsyncClient",
        lambda **kwargs: _FakeHttpClient(response),
    )


@pytest.mark.asyncio
async def test_edit_reports_success() -> None:
    with _with_http(httpx.Response(200, json={"ok": True})):
        assert await edit_html_message(1001, 10, "Считаю аспекты ✨") is True


@pytest.mark.asyncio
async def test_edit_treats_not_modified_as_success() -> None:
    """Стадия повторилась с тем же текстом — сообщение и так верное."""
    response = httpx.Response(
        400,
        json={"ok": False, "description": "Bad Request: message is not modified"},
    )
    with _with_http(response):
        assert await edit_html_message(1001, 10, "Считаю аспекты ✨") is True


@pytest.mark.asyncio
async def test_edit_reports_failure_when_message_gone() -> None:
    """Человек удалил сообщение — зовущий должен отправить новое."""
    response = httpx.Response(
        400,
        json={"ok": False, "description": "Bad Request: message to edit not found"},
    )
    with _with_http(response):
        assert await edit_html_message(1001, 10, "Считаю аспекты ✨") is False


@pytest.mark.asyncio
async def test_edit_survives_network_error() -> None:
    with _with_http(httpx.ConnectError("no route")):
        assert await edit_html_message(1001, 10, "Считаю аспекты ✨") is False
