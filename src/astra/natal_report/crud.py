"""CRUD для natal_reports."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.natal_report.enums import NatalReportStatus
from astra.natal_report.models import NatalReport


async def create_natal_report(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    subject_snapshot: dict,
    chart_data: dict,
    features: dict,
    title: str,
) -> NatalReport:
    row = NatalReport(
        owner_user_id=owner_user_id,
        subject_snapshot=subject_snapshot,
        chart_data=chart_data,
        features=features,
        title=title,
        status=NatalReportStatus.CHART_READY,
    )
    session.add(row)
    await session.flush()
    return row


async def get_natal_report(
    session: AsyncSession,
    report_id: uuid.UUID,
) -> NatalReport | None:
    result = await session.execute(
        select(NatalReport).where(NatalReport.id == report_id),
    )
    return result.scalar_one_or_none()


async def get_latest_natal_report_for_user(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
) -> NatalReport | None:
    result = await session.execute(
        select(NatalReport)
        .where(NatalReport.owner_user_id == owner_user_id)
        .order_by(NatalReport.created_at.desc())
        .limit(1),
    )
    return result.scalar_one_or_none()


async def mark_natal_generating(session: AsyncSession, report: NatalReport) -> None:
    report.status = NatalReportStatus.GENERATING
    await session.flush()


async def mark_natal_text_ready(
    session: AsyncSession,
    report: NatalReport,
    llm_output: dict,
) -> None:
    report.status = NatalReportStatus.TEXT_READY
    report.llm_output = llm_output
    report.failure_reason = None
    await session.flush()


async def mark_natal_ready(
    session: AsyncSession,
    report: NatalReport,
    *,
    pdf_path: str,
) -> None:
    report.status = NatalReportStatus.READY
    report.pdf_path = pdf_path
    report.failure_reason = None
    await session.flush()


async def mark_natal_failed(
    session: AsyncSession,
    report: NatalReport,
    reason: str,
) -> None:
    report.status = NatalReportStatus.FAILED
    report.failure_reason = reason[:2000]
    await session.flush()


async def mark_natal_sent(session: AsyncSession, report: NatalReport) -> None:
    report.sent_at = datetime.now(timezone.utc)
    await session.flush()
