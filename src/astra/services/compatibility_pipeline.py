"""Старт и возобновление пайплайна совместимости."""

from __future__ import annotations

import uuid

from astra.compatibility.enums import ReportStatus
from astra.compatibility.models import CompatibilityReport
from astra.messaging.publisher import (
    publish_compatibility_generate,
    publish_compatibility_send,
    publish_pdf_generate,
    publish_synastry_build,
)


async def enqueue_compatibility_pipeline(report_id: uuid.UUID) -> None:
    await publish_synastry_build(report_id)


async def resume_compatibility_pipeline(report: CompatibilityReport) -> None:
    status = ReportStatus(report.status)
    if status in {
        ReportStatus.PENDING,
        ReportStatus.FAILED,
        ReportStatus.GENERATING,
    }:
        await publish_synastry_build(report.id)
        return
    if status == ReportStatus.SYNASTRY_READY:
        await publish_compatibility_generate(report.id)
        return
    if status == ReportStatus.TEXT_READY:
        await publish_pdf_generate(report.id)
        return
    if status == ReportStatus.READY and report.sent_at is None:
        await publish_compatibility_send(report.id)
