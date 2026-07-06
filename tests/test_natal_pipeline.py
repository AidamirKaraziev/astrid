"""Тесты пайплайна разбора натала: очередь, worker, caption, статусы."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from astra.messaging.schemas import TaskMessage, TaskType
from astra.natal_report.enums import NatalReportStatus
from astra.services.natal_pipeline import enqueue_natal_pipeline, resume_natal_pipeline
from astra.workers import handlers


@pytest.mark.asyncio
async def test_enqueue_natal_pipeline_starts_with_generate() -> None:
    report_id = uuid4()
    with patch(
        "astra.services.natal_pipeline.publish_natal_generate",
        new=AsyncMock(),
    ) as publish_mock:
        await enqueue_natal_pipeline(report_id)
    publish_mock.assert_awaited_once_with(report_id)


@pytest.mark.asyncio
async def test_resume_natal_pipeline_by_status() -> None:
    report = MagicMock()
    report.id = uuid4()
    report.sent_at = None

    cases = [
        (NatalReportStatus.CHART_READY, "publish_natal_generate"),
        (NatalReportStatus.TEXT_READY, "publish_natal_pdf_generate"),
        (NatalReportStatus.READY, "publish_natal_send"),
    ]
    for status, expected in cases:
        report.status = status.value
        with (
            patch(
                "astra.services.natal_pipeline.publish_natal_generate",
                new=AsyncMock(),
            ) as p_gen,
            patch(
                "astra.services.natal_pipeline.publish_natal_pdf_generate",
                new=AsyncMock(),
            ) as p_pdf,
            patch(
                "astra.services.natal_pipeline.publish_natal_send",
                new=AsyncMock(),
            ) as p_send,
        ):
            await resume_natal_pipeline(report)
        mocks = {
            "publish_natal_generate": p_gen,
            "publish_natal_pdf_generate": p_pdf,
            "publish_natal_send": p_send,
        }
        for name, mock in mocks.items():
            if name == expected:
                mock.assert_awaited_once_with(report.id)
            else:
                mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_natal_generate_publishes_pdf_task() -> None:
    report_id = uuid4()
    user_id = uuid4()
    report = MagicMock()
    report.id = report_id
    report.owner_user_id = user_id
    user = MagicMock()
    user.id = user_id
    user.telegram_id = 1001
    session = AsyncMock()
    task = TaskMessage(type=TaskType.NATAL_GENERATE, report_id=report_id)

    with (
        patch(
            "astra.workers.handlers.generate_natal_llm",
            new=AsyncMock(return_value=report),
        ),
        patch(
            "astra.workers.handlers.users_crud.get_user_by_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "astra.workers.handlers.notify_natal_stage",
            new=AsyncMock(),
        ) as notify_mock,
        patch(
            "astra.workers.handlers.publish_natal_pdf_generate",
            new=AsyncMock(),
        ) as publish_mock,
        patch(
            "astra.workers.handlers.send_chat_action_typing",
            new=AsyncMock(),
        ),
        patch(
            "astra.natal_report.crud.get_natal_report",
            new=AsyncMock(return_value=report),
        ),
    ):
        await handlers.handle_natal_generate(session, task)

    publish_mock.assert_awaited_once_with(report_id)
    notify_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_natal_pdf_generate_publishes_send() -> None:
    report_id = uuid4()
    report = MagicMock()
    report.id = report_id
    session = AsyncMock()
    task = TaskMessage(type=TaskType.NATAL_PDF_GENERATE, report_id=report_id)

    with (
        patch(
            "astra.workers.handlers.generate_natal_report_pdf",
            new=AsyncMock(return_value=report),
        ),
        patch(
            "astra.workers.handlers.publish_natal_send",
            new=AsyncMock(),
        ) as publish_mock,
    ):
        await handlers.handle_natal_pdf_generate(session, task)

    publish_mock.assert_awaited_once_with(report_id)


@pytest.mark.asyncio
async def test_dispatch_routes_natal_tasks() -> None:
    session = AsyncMock()
    for task_type, handler_name in [
        (TaskType.NATAL_GENERATE, "handle_natal_generate"),
        (TaskType.NATAL_PDF_GENERATE, "handle_natal_pdf_generate"),
        (TaskType.NATAL_SEND, "handle_natal_send"),
    ]:
        task = TaskMessage(type=task_type, report_id=uuid4())
        with patch.object(handlers, handler_name, new=AsyncMock()) as handler_mock:
            await handlers.dispatch_task(session, task)
        handler_mock.assert_awaited_once()


def test_format_natal_pdf_caption_with_tldr() -> None:
    from astra.services.natal_report_service import format_natal_pdf_caption

    report = MagicMock()
    report.title = "Натальная карта · Айдамир"
    report.llm_output = {"tldr": "Краткий итог карты."}
    caption = format_natal_pdf_caption(report)
    assert caption.startswith("Краткий итог карты.")
    assert caption.endswith("🌌 Натальная карта · Айдамир")


def test_format_natal_pdf_caption_clamps_to_telegram_limit() -> None:
    from astra.services.natal_report_service import format_natal_pdf_caption

    report = MagicMock()
    report.title = "Натальная карта · Айдамир"
    report.llm_output = {"tldr": "х" * 2000}
    caption = format_natal_pdf_caption(report)
    assert len(caption) <= 1024
    assert caption.endswith("🌌 Натальная карта · Айдамир")


@pytest.mark.asyncio
async def test_generate_pdf_from_jsonb_snapshots(tmp_path) -> None:
    """Полный путь из JSONB: chart_data + llm_output как dict из БД → PDF."""
    pytest.importorskip("kerykeion")
    from datetime import date, datetime

    from astra.astro.calculator import build_full_natal_chart
    from astra.astro.chart_features import build_chart_features
    from astra.llm.natal_assemble import assemble_llm_output, build_natal_prompt_input
    from astra.services import natal_report_service as svc
    from test_natal_assemble import _content_raw

    chart = build_full_natal_chart(
        name="Тест",
        birth_date=date(1990, 6, 15),
        birth_time=datetime(1990, 6, 15, 14, 30),
        lat=55.7558,
        lon=37.6176,
        timezone="Europe/Moscow",
    )
    prompt_input = build_natal_prompt_input(
        chart,
        build_chart_features(chart),
        name="Айдамир",
        gender="м",
        birth_date=date(1990, 6, 15),
        birth_time_label="14:30",
        birth_place="Москва",
    )
    output = assemble_llm_output(_content_raw(prompt_input, with_asc=True), prompt_input)

    report = MagicMock()
    report.id = uuid4()
    report.status = NatalReportStatus.TEXT_READY.value
    report.pdf_path = None
    report.chart_data = chart.model_dump(mode="json")  # как из JSONB
    report.llm_output = output.model_dump(mode="json")
    report.subject_snapshot = {
        "name": "Айдамир",
        "birth_date": "1990-06-15",
        "birth_time": "1990-06-15T14:30:00",
        "birth_place": "Москва",
    }
    session = AsyncMock()

    marked = {}

    async def _mark_ready(sess, rep, *, pdf_path):
        marked["pdf_path"] = pdf_path

    settings = MagicMock()
    settings.natal_pdf_dir = str(tmp_path)
    with (
        patch(
            "astra.services.natal_report_service.get_settings",
            return_value=settings,
        ),
        patch(
            "astra.services.natal_report_service.natal_crud.get_natal_report",
            new=AsyncMock(return_value=report),
        ),
        patch(
            "astra.services.natal_report_service.natal_crud.mark_natal_ready",
            new=_mark_ready,
        ),
    ):
        result = await svc.generate_natal_report_pdf(session, report.id)

    assert result is not None
    from pathlib import Path

    pdf = Path(marked["pdf_path"])
    assert pdf.is_file() and pdf.stat().st_size > 10_000


@pytest.mark.asyncio
async def test_create_natal_report_with_gender_str(tmp_path) -> None:
    """Регрессия: Gender — Literal[str], а не enum; .value падал с AttributeError."""
    pytest.importorskip("kerykeion")
    from datetime import date, datetime

    from astra.services.natal_report_service import create_natal_report_for_user

    profile = MagicMock()
    profile.display_name = "Айдамир"
    profile.gender = "мужчина"  # str, не enum
    profile.birth_date = date(1990, 6, 15)
    profile.birth_time = datetime(1990, 6, 15, 14, 30)
    profile.birth_place = "Москва"
    profile.birth_place_id = None
    profile.timezone = "Europe/Moscow"
    user = MagicMock()
    user.id = uuid4()
    user.profile = profile
    session = AsyncMock()

    created = {}

    async def _create(sess, **kwargs):
        created.update(kwargs)
        row = MagicMock()
        row.id = uuid4()
        return row

    with patch(
        "astra.services.natal_report_service.natal_crud.create_natal_report",
        new=_create,
    ):
        report = await create_natal_report_for_user(session, user)

    assert report is not None
    assert created["subject_snapshot"]["gender"] == "мужчина"
    assert created["chart_data"]["has_time"] is True
