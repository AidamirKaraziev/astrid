from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from astra.compatibility.enums import ReportStatus
from astra.messaging.schemas import TaskMessage, TaskType
from astra.services.compatibility_pipeline import (
    enqueue_compatibility_pipeline,
    resume_compatibility_pipeline,
)
from astra.workers import handlers


@pytest.mark.asyncio
async def test_enqueue_compatibility_pipeline_starts_with_synastry() -> None:
    report_id = uuid4()
    with patch(
        "astra.services.compatibility_pipeline.publish_synastry_build",
        new=AsyncMock(),
    ) as publish_mock:
        await enqueue_compatibility_pipeline(report_id)
    publish_mock.assert_awaited_once_with(report_id)


@pytest.mark.asyncio
async def test_resume_compatibility_pipeline_from_text_ready() -> None:
    report = MagicMock()
    report.id = uuid4()
    report.status = ReportStatus.TEXT_READY.value
    report.sent_at = None

    with (
        patch(
            "astra.services.compatibility_pipeline.publish_pdf_generate",
            new=AsyncMock(),
        ) as publish_pdf,
        patch(
            "astra.services.compatibility_pipeline.publish_compatibility_send",
            new=AsyncMock(),
        ) as publish_send,
    ):
        await resume_compatibility_pipeline(report)

    publish_pdf.assert_awaited_once_with(report.id)
    publish_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_synastry_build_publishes_llm_task() -> None:
    report_id = uuid4()
    user_id = uuid4()
    report = MagicMock()
    report.id = report_id
    report.owner_user_id = user_id
    user = MagicMock()
    user.id = user_id
    user.telegram_id = 1001
    session = AsyncMock()
    task = TaskMessage(type=TaskType.SYNASTRY_BUILD, report_id=report_id)

    with (
        patch(
            "astra.workers.handlers.build_and_store_synastry",
            new=AsyncMock(return_value=report),
        ),
        patch(
            "astra.workers.handlers.users_crud.get_user_by_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "astra.workers.handlers.notify_compatibility_stage",
            new=AsyncMock(),
        ),
        patch(
            "astra.workers.handlers.publish_compatibility_generate",
            new=AsyncMock(),
        ) as publish_mock,
    ):
        await handlers.handle_synastry_build(session, task)

    publish_mock.assert_awaited_once_with(report_id)


@pytest.mark.asyncio
async def test_handle_pdf_generate_publishes_send_task() -> None:
    report_id = uuid4()
    report = MagicMock()
    report.id = report_id
    session = AsyncMock()
    task = TaskMessage(type=TaskType.PDF_GENERATE, report_id=report_id)

    with (
        patch(
            "astra.workers.handlers.generate_compatibility_pdf",
            new=AsyncMock(return_value=report),
        ),
        patch(
            "astra.workers.handlers.publish_compatibility_send",
            new=AsyncMock(),
        ) as publish_mock,
    ):
        await handlers.handle_pdf_generate(session, task)

    publish_mock.assert_awaited_once_with(report_id)
