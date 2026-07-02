from datetime import date
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

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
async def test_advance_progress_deletes_previous_and_saves_new() -> None:
    user_id = uuid4()
    chat_id = 1001
    job_key = "prediction:2026-07-02"

    with (
        patch(
            "astra.telegram.progress.notifier.get_progress_message_id",
            new=AsyncMock(return_value=10),
        ),
        patch(
            "astra.telegram.progress.notifier.delete_message",
            new=AsyncMock(return_value=True),
        ) as delete_mock,
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
    delete_mock.assert_awaited_once_with(chat_id, 10, settings=None)
    typing_mock.assert_awaited_once()
    send_mock.assert_awaited_once()
    save_mock.assert_awaited_once_with(user_id, job_key, 11)


@pytest.mark.asyncio
async def test_advance_progress_skips_delete_when_no_previous() -> None:
    user_id = uuid4()
    chat_id = 1001
    job_key = "prediction:2026-07-02"

    with (
        patch(
            "astra.telegram.progress.notifier.get_progress_message_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "astra.telegram.progress.notifier.delete_message",
            new=AsyncMock(),
        ) as delete_mock,
        patch(
            "astra.telegram.progress.notifier.send_chat_action_typing",
            new=AsyncMock(),
        ),
        patch(
            "astra.telegram.progress.notifier.send_html_message",
            new=AsyncMock(return_value=5),
        ),
        patch(
            "astra.telegram.progress.notifier.set_progress_message_id",
            new=AsyncMock(),
        ),
    ):
        await advance_progress(chat_id, user_id, job_key, "Старт ✨", with_typing=False)

    delete_mock.assert_not_awaited()


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
