"""Старт и возобновление пайплайна разбора натала."""

from __future__ import annotations

import uuid

from astra.messaging.publisher import (
    publish_natal_generate,
    publish_natal_pdf_generate,
    publish_natal_send,
)
from astra.natal_report.enums import NatalReportStatus
from astra.natal_report.models import NatalReport


async def enqueue_natal_pipeline(report_id: uuid.UUID) -> None:
    await publish_natal_generate(report_id)


async def resume_natal_pipeline(report: NatalReport) -> None:
    status = NatalReportStatus(report.status)
    if status in {
        NatalReportStatus.PENDING,
        NatalReportStatus.FAILED,
        NatalReportStatus.GENERATING,
        NatalReportStatus.CHART_READY,
    }:
        await publish_natal_generate(report.id)
        return
    if status == NatalReportStatus.TEXT_READY:
        await publish_natal_pdf_generate(report.id)
        return
    if status == NatalReportStatus.READY and report.sent_at is None:
        await publish_natal_send(report.id)
