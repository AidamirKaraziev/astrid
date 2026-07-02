"""CRUD для natal_profiles и compatibility_reports."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.compatibility.enums import ReportStatus
from astra.compatibility.models import CompatibilityReport, NatalProfile


async def get_natal_profile_by_id(
    session: AsyncSession,
    profile_id: uuid.UUID,
) -> NatalProfile | None:
    result = await session.execute(
        select(NatalProfile).where(NatalProfile.id == profile_id),
    )
    return result.scalar_one_or_none()


async def find_natal_profile_by_label(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    label: str,
) -> NatalProfile | None:
    normalized = label.strip()
    result = await session.execute(
        select(NatalProfile).where(
            NatalProfile.owner_user_id == owner_user_id,
            NatalProfile.label == normalized,
        ),
    )
    return result.scalar_one_or_none()


async def upsert_natal_profile(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    label: str,
    gender: str | None,
    birth_date,
    birth_time: datetime | None,
    birth_place: str,
    birth_place_id: uuid.UUID | None,
    timezone: str,
    chart_data: dict | None = None,
) -> NatalProfile:
    existing = await find_natal_profile_by_label(session, owner_user_id, label)
    if existing is None:
        row = NatalProfile(
            owner_user_id=owner_user_id,
            label=label.strip(),
            gender=gender,  # type: ignore[arg-type]
            birth_date=birth_date,
            birth_time=birth_time,
            birth_place=birth_place,
            birth_place_id=birth_place_id,
            timezone=timezone,
            chart_data=chart_data,
        )
        session.add(row)
        await session.flush()
        return row

    existing.gender = gender  # type: ignore[assignment]
    existing.birth_date = birth_date
    existing.birth_time = birth_time
    existing.birth_place = birth_place
    existing.birth_place_id = birth_place_id
    existing.timezone = timezone
    if chart_data is not None:
        existing.chart_data = chart_data
    await session.flush()
    return existing


async def create_compatibility_report(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    relationship_context: str,
    pair_mode: str,
    person_a_natal_profile_id: uuid.UUID | None,
    person_b_natal_profile_id: uuid.UUID | None,
    person_a_snapshot: dict,
    person_b_snapshot: dict,
    title: str,
) -> CompatibilityReport:
    row = CompatibilityReport(
        owner_user_id=owner_user_id,
        relationship_context=relationship_context,
        pair_mode=pair_mode,
        person_a_natal_profile_id=person_a_natal_profile_id,
        person_b_natal_profile_id=person_b_natal_profile_id,
        person_a_snapshot=person_a_snapshot,
        person_b_snapshot=person_b_snapshot,
        title=title,
        status=ReportStatus.PENDING,
    )
    session.add(row)
    await session.flush()
    return row


async def get_compatibility_report(
    session: AsyncSession,
    report_id: uuid.UUID,
) -> CompatibilityReport | None:
    result = await session.execute(
        select(CompatibilityReport).where(CompatibilityReport.id == report_id),
    )
    return result.scalar_one_or_none()


async def list_compatibility_reports(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    limit: int = 20,
) -> list[CompatibilityReport]:
    result = await session.execute(
        select(CompatibilityReport)
        .where(CompatibilityReport.owner_user_id == owner_user_id)
        .order_by(CompatibilityReport.created_at.desc())
        .limit(limit),
    )
    return list(result.scalars().all())


async def mark_report_synastry_ready(
    session: AsyncSession,
    report: CompatibilityReport,
    astro_context: dict,
) -> None:
    report.status = ReportStatus.SYNASTRY_READY
    report.astro_context = astro_context
    report.failure_reason = None
    await session.flush()


async def mark_report_text_ready(
    session: AsyncSession,
    report: CompatibilityReport,
    llm_output: dict,
) -> None:
    report.status = ReportStatus.TEXT_READY
    report.llm_output = llm_output
    report.failure_reason = None
    await session.flush()


async def mark_report_generating(session: AsyncSession, report: CompatibilityReport) -> None:
    report.status = ReportStatus.GENERATING
    await session.flush()


async def mark_report_ready(
    session: AsyncSession,
    report: CompatibilityReport,
    *,
    llm_output: dict,
    astro_context: dict,
    pdf_path: str,
) -> None:
    report.status = ReportStatus.READY
    report.llm_output = llm_output
    report.astro_context = astro_context
    report.pdf_path = pdf_path
    report.failure_reason = None
    await session.flush()


async def mark_report_failed(
    session: AsyncSession,
    report: CompatibilityReport,
    reason: str,
) -> None:
    report.status = ReportStatus.FAILED
    report.failure_reason = reason[:2000]
    await session.flush()


async def mark_report_sent(session: AsyncSession, report: CompatibilityReport) -> None:
    report.sent_at = datetime.now(timezone.utc)
    await session.flush()


async def delete_compatibility_report(session: AsyncSession, report_id: uuid.UUID) -> bool:
    result = await session.execute(
        delete(CompatibilityReport).where(CompatibilityReport.id == report_id),
    )
    await session.flush()
    return (result.rowcount or 0) > 0
