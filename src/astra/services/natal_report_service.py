"""Оркестрация разбора натала: карта → LLM → PDF → Telegram."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from astra.astro.calculator import build_full_natal_chart
from astra.astro.chart_features import ChartFeatures, build_chart_features
from astra.astro.schemas import FullNatalChart
from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger
from astra.llm.factory import get_deepseek_provider
from astra.llm.natal_assemble import build_natal_prompt_input
from astra.llm.natal_generate import generate_natal_output
from astra.llm.schemas.natal import NatalLlmOutput
from astra.natal_report import crud as natal_crud
from astra.natal_report.enums import NATAL_IN_FLIGHT_STATUSES, NatalReportStatus
from astra.natal_report.models import NatalReport
from astra.places import crud as places_crud
from astra.reports.natal.builder import generate_natal_pdf
from astra.reports.natal.fonts import register_natal_fonts
from astra.reports.natal.mapper import llm_output_to_report_data
from astra.services.natal_pipeline import enqueue_natal_pipeline, resume_natal_pipeline
from astra.users import crud as users_crud
from astra.users.models import Profile, User

log = get_logger(__name__)


class NatalRequestStatus(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class NatalRequestOutcome:
    status: NatalRequestStatus
    report_id: uuid.UUID | None = None


async def _coordinates(
    session: AsyncSession,
    *,
    birth_place_id: uuid.UUID | None,
    timezone: str,
) -> tuple[float, float, str]:
    if birth_place_id:
        place = await places_crud.get_place_by_id(session, birth_place_id)
        if place is not None:
            return float(place.latitude), float(place.longitude), place.timezone
    return 55.75, 37.62, timezone


def _birth_time_label(birth_time: datetime | None) -> str | None:
    return birth_time.strftime("%H:%M") if birth_time else None


def build_natal_title(name: str) -> str:
    return f"Натальная карта · {name}"


def person_subtitle(
    birth_date: date,
    birth_time: datetime | None,
    birth_place: str | None,
) -> str:
    parts = [birth_date.strftime("%d.%m.%Y")]
    if birth_time is not None:
        parts.append(birth_time.strftime("%H:%M"))
    if birth_place:
        parts.append(birth_place)
    return " · ".join(parts)


async def create_natal_report_for_user(
    session: AsyncSession,
    user: User,
) -> NatalReport:
    """Создать отчёт: полная карта и фичи считаются инлайн (<100 мс)."""
    profile: Profile | None = user.profile
    if profile is None:
        msg = "profile required"
        raise ValueError(msg)

    lat, lon, tz = await _coordinates(
        session,
        birth_place_id=profile.birth_place_id,
        timezone=profile.timezone,
    )
    chart = build_full_natal_chart(
        name=profile.display_name,
        birth_date=profile.birth_date,
        birth_time=profile.birth_time,
        lat=lat,
        lon=lon,
        timezone=tz,
    )
    features = build_chart_features(chart)

    snapshot = {
        "name": profile.display_name,
        "gender": profile.gender,  # Gender = Literal[str], не enum
        "birth_date": profile.birth_date.isoformat(),
        "birth_time": profile.birth_time.isoformat() if profile.birth_time else None,
        "birth_place": profile.birth_place,
        "timezone": tz,
    }

    report = await natal_crud.create_natal_report(
        session,
        owner_user_id=user.id,
        subject_snapshot=snapshot,
        chart_data=chart.model_dump(),
        features=features.model_dump(),
        title=build_natal_title(profile.display_name),
    )
    log.info(Event.NATAL_REPORT_CREATED, report_id=report.id, has_time=chart.has_time)
    return report


def _prompt_input_from_report(report: NatalReport):
    chart = FullNatalChart.model_validate(report.chart_data)
    features = ChartFeatures.model_validate(report.features or {})
    snap = report.subject_snapshot
    birth_time = (
        datetime.fromisoformat(snap["birth_time"]) if snap.get("birth_time") else None
    )
    return build_natal_prompt_input(
        chart,
        features,
        name=str(snap["name"]),
        gender=snap.get("gender"),
        birth_date=date.fromisoformat(str(snap["birth_date"])),
        birth_time_label=_birth_time_label(birth_time),
        birth_place=str(snap.get("birth_place") or "не указано"),
    )


async def generate_natal_llm(
    session: AsyncSession,
    report_id: uuid.UUID,
) -> NatalReport | None:
    settings = get_settings()
    report = await natal_crud.get_natal_report(session, report_id)
    if report is None:
        log.warning(Event.NATAL_REPORT_MISSING, report_id=report_id)
        return None
    if report.status in {NatalReportStatus.TEXT_READY, NatalReportStatus.READY} and report.llm_output:
        return report

    deepseek = get_deepseek_provider(settings)
    if not deepseek.is_configured():
        await natal_crud.mark_natal_failed(session, report, "deepseek_disabled")
        return None

    try:
        prompt_input = _prompt_input_from_report(report)
        output, failure = await generate_natal_output(prompt_input, deepseek, settings)
        if output is None:
            log.error(Event.NATAL_REPORT_LLM_FAILED, report_id=report_id, reason=failure)
            await natal_crud.mark_natal_failed(session, report, failure or "llm_failed")
            user = await users_crud.get_user_by_id(session, report.owner_user_id)
            if user is not None:
                from astra.services.natal_failure_notify import (
                    send_natal_failure_notification,
                )

                await send_natal_failure_notification(user.telegram_id)
            return None
        await natal_crud.mark_natal_text_ready(session, report, output.model_dump())
        return report
    except Exception as exc:
        log.exception(Event.NATAL_REPORT_LLM_FAILED, report_id=report_id)
        await natal_crud.mark_natal_failed(session, report, str(exc))
        return None


def pdf_path_for_natal_report(settings: Settings, report: NatalReport) -> Path:
    base = Path(settings.natal_pdf_dir)
    name = str(report.subject_snapshot.get("name") or "natal")
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_ ").strip() or "natal"
    return base / f"natal_{safe}_{report.id.hex[:8]}.pdf"


async def generate_natal_report_pdf(
    session: AsyncSession,
    report_id: uuid.UUID,
) -> NatalReport | None:
    settings = get_settings()
    report = await natal_crud.get_natal_report(session, report_id)
    if report is None:
        log.warning(Event.NATAL_REPORT_MISSING, report_id=report_id)
        return None
    if report.status == NatalReportStatus.READY and report.pdf_path:
        return report
    if not report.llm_output:
        await natal_crud.mark_natal_failed(session, report, "missing_llm_output")
        return None

    try:
        chart = FullNatalChart.model_validate(report.chart_data)
        output = NatalLlmOutput.model_validate(report.llm_output)
        snap = report.subject_snapshot
        birth_time = (
            datetime.fromisoformat(snap["birth_time"]) if snap.get("birth_time") else None
        )
        report_data = llm_output_to_report_data(
            output,
            chart,
            person_name=str(snap["name"]),
            person_subtitle=person_subtitle(
                date.fromisoformat(str(snap["birth_date"])),
                birth_time,
                snap.get("birth_place"),
            ),
        )
        out_path = pdf_path_for_natal_report(settings, report)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        register_natal_fonts()
        generate_natal_pdf(str(out_path), report_data)
        await natal_crud.mark_natal_ready(session, report, pdf_path=str(out_path))
        return report
    except Exception as exc:
        log.exception(Event.NATAL_REPORT_PDF_FAILED, report_id=report_id)
        await natal_crud.mark_natal_failed(session, report, str(exc))
        return None


_TELEGRAM_DOCUMENT_CAPTION_MAX = 1024


def format_natal_pdf_caption(report: NatalReport) -> str:
    footer = f"🌌 {report.title}"
    tldr = _report_tldr(report)
    if not tldr:
        return footer
    caption = f"{tldr}\n\n{footer}"
    if len(caption) <= _TELEGRAM_DOCUMENT_CAPTION_MAX:
        return caption
    ellipsis = "…"
    budget = _TELEGRAM_DOCUMENT_CAPTION_MAX - len(f"\n\n{footer}") - len(ellipsis)
    if budget < 1:
        return footer[:_TELEGRAM_DOCUMENT_CAPTION_MAX]
    return f"{tldr[:budget].rstrip()}{ellipsis}\n\n{footer}"


def _report_tldr(report: NatalReport) -> str | None:
    if not report.llm_output:
        return None
    try:
        tldr = NatalLlmOutput.model_validate(report.llm_output).tldr.strip()
    except Exception:
        raw = report.llm_output.get("tldr")
        tldr = raw.strip() if isinstance(raw, str) else ""
    return tldr or None


async def deliver_natal_report(
    session: AsyncSession,
    report_id: uuid.UUID,
    *,
    resend: bool = False,
) -> bool:
    report = await natal_crud.get_natal_report(session, report_id)
    if report is None or report.status != NatalReportStatus.READY or not report.pdf_path:
        return False
    if report.sent_at is not None and not resend:
        return True

    user = await users_crud.get_user_by_id(session, report.owner_user_id)
    if user is None:
        return False

    pdf_path = Path(report.pdf_path)
    if not pdf_path.is_file():
        await natal_crud.mark_natal_failed(session, report, "pdf_missing")
        return False

    from astra.workers.telegram_send import send_compatibility_pdf

    await send_compatibility_pdf(
        user.telegram_id,
        pdf_path,
        caption=format_natal_pdf_caption(report),
    )
    await natal_crud.mark_natal_sent(session, report)
    return True


async def request_natal_report(
    session: AsyncSession,
    report_id: uuid.UUID,
) -> NatalRequestOutcome:
    report = await natal_crud.get_natal_report(session, report_id)
    if report is None:
        return NatalRequestOutcome(status=NatalRequestStatus.FAILED)

    status = NatalReportStatus(report.status)
    if status in NATAL_IN_FLIGHT_STATUSES and report.sent_at is None and status != NatalReportStatus.CHART_READY:
        return NatalRequestOutcome(
            status=NatalRequestStatus.IN_PROGRESS,
            report_id=report_id,
        )
    if status == NatalReportStatus.FAILED:
        return NatalRequestOutcome(status=NatalRequestStatus.FAILED, report_id=report_id)

    await resume_natal_pipeline(report)
    return NatalRequestOutcome(status=NatalRequestStatus.QUEUED, report_id=report_id)


async def enqueue_natal_report(report_id: uuid.UUID) -> None:
    await enqueue_natal_pipeline(report_id)
