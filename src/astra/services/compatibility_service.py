"""Оркестрация заказа совместимости: astro → LLM → PDF → Telegram."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from astra.astro.calculator import build_natal_chart, build_natal_chart_for_birth
from astra.astro.schemas import NatalChartData
from astra.astro.synastry import (
    PersonSpec,
    build_synastry_aspects,
    chart_to_natal_dict,
    natal_profile_accuracy_tier,
    profile_accuracy_tier,
    snapshot_from_natal_profile,
    snapshot_from_profile,
)
from astra.compatibility import crud as compatibility_crud
from astra.compatibility.enums import (
    COMPATIBILITY_IN_FLIGHT_STATUSES,
    RELATIONSHIP_LABELS,
    PairMode,
    RelationshipContext,
    ReportStatus,
)
from astra.compatibility.models import CompatibilityReport, NatalProfile
from astra.core.config import Settings, get_settings
from astra.llm.compatibility_generate import generate_compatibility_output
from astra.llm.factory import get_deepseek_provider
from astra.llm.schemas.compatibility import (
    CompatibilityLlmOutput,
    CompatibilityPersonInput,
    CompatibilityPromptInput,
    SynastryAspectInput,
)
from astra.places import crud as places_crud
from astra.reports.synastry import generate_synastry_pdf
from astra.reports.synastry.mapper import llm_output_to_report_data
from astra.users import crud as users_crud
from astra.users.models import Profile, User
from astra.services.compatibility_pdf_filenames import (
    build_pdf_download_filename_from_report,
    pdf_path_for_report_file,
)
from astra.services.compatibility_pipeline import (
    enqueue_compatibility_pipeline,
    resume_compatibility_pipeline,
)

logger = logging.getLogger(__name__)


class CompatibilityRequestStatus(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CompatibilityRequestOutcome:
    status: CompatibilityRequestStatus
    report_id: uuid.UUID | None = None


def _birth_time_hhmm(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        if "T" in raw:
            dt = datetime.fromisoformat(raw)
            return dt.strftime("%H:%M")
        return raw[:5]
    except ValueError:
        return None


def _parse_birth_time_iso(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def person_input_from_snapshot(snap: dict) -> CompatibilityPersonInput:
    gender = snap.get("gender") or "не указан"
    return CompatibilityPersonInput(
        name=str(snap["name"]),
        gender=str(gender),
        birth_date=date.fromisoformat(str(snap["birth_date"])),
        birth_time=_birth_time_hhmm(snap.get("birth_time")),
        birth_place=str(snap.get("birth_place") or "не указан"),
        timezone=str(snap.get("timezone") or "Europe/Moscow"),
        accuracy_tier=int(snap.get("accuracy_tier") or 33),
        natal=dict(snap.get("natal") or {}),
    )


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


async def chart_for_profile(session: AsyncSession, profile: Profile) -> NatalChartData:
    place_id = profile.birth_place_id
    lat, lon, tz = await _coordinates(
        session,
        birth_place_id=place_id,
        timezone=profile.timezone,
    )
    return build_natal_chart(profile, lat=lat, lon=lon, timezone=tz)


async def chart_for_natal_profile(session: AsyncSession, row: NatalProfile) -> NatalChartData:
    if row.chart_data:
        return NatalChartData.model_validate(row.chart_data)
    lat, lon, tz = await _coordinates(
        session,
        birth_place_id=row.birth_place_id,
        timezone=row.timezone,
    )
    tier = natal_profile_accuracy_tier(row)
    chart = build_natal_chart_for_birth(
        name=row.label,
        birth_date=row.birth_date,
        birth_time=row.birth_time,
        lat=lat,
        lon=lon,
        timezone=tz,
        accuracy_tier=tier,
    )
    row.chart_data = chart.model_dump()
    return chart


def build_report_title(
    person_a_name: str,
    person_b_name: str,
    context: RelationshipContext,
) -> str:
    ctx = RELATIONSHIP_LABELS.get(context, str(context))
    return f"{person_a_name} × {person_b_name} · {ctx}"


def pdf_filename(report: CompatibilityReport) -> str:
    return build_pdf_download_filename_from_report(report)


def pdf_path_for_report(settings: Settings, report: CompatibilityReport) -> Path:
    base = Path(settings.compatibility_pdf_dir)
    filename = pdf_filename(report)
    return pdf_path_for_report_file(base, filename, report.id)


async def _compute_prompt_input_from_snapshots(
    session: AsyncSession,
    report: CompatibilityReport,
) -> CompatibilityPromptInput:
    person_a = person_input_from_snapshot(report.person_a_snapshot)
    person_b = person_input_from_snapshot(report.person_b_snapshot)

    chart_a = NatalChartData.model_validate(
        {
            **report.person_a_snapshot.get("chart", {}),
            "accuracy_tier": person_a.accuracy_tier,
            "sun_sign": person_a.natal.get("sun", "—"),
            "moon_sign": person_a.natal.get("moon"),
            "asc_sign": person_a.natal.get("asc"),
            "planet_signs": {
                k: v
                for k, v in person_a.natal.items()
                if k in ("mercury", "venus", "mars", "jupiter", "saturn")
            },
            "timezone": person_a.timezone,
        },
    )
    chart_b = NatalChartData.model_validate(
        {
            **report.person_b_snapshot.get("chart", {}),
            "accuracy_tier": person_b.accuracy_tier,
            "sun_sign": person_b.natal.get("sun", "—"),
            "moon_sign": person_b.natal.get("moon"),
            "asc_sign": person_b.natal.get("asc"),
            "planet_signs": {
                k: v
                for k, v in person_b.natal.items()
                if k in ("mercury", "venus", "mars", "jupiter", "saturn")
            },
            "timezone": person_b.timezone,
        },
    )

    spec_a = PersonSpec(
        name=person_a.name,
        birth_date=person_a.birth_date,
        birth_time=_parse_birth_time_iso(report.person_a_snapshot.get("birth_time")),
        timezone=person_a.timezone,
        chart=chart_a,
    )
    spec_b = PersonSpec(
        name=person_b.name,
        birth_date=person_b.birth_date,
        birth_time=_parse_birth_time_iso(report.person_b_snapshot.get("birth_time")),
        timezone=person_b.timezone,
        chart=chart_b,
    )
    aspects = build_synastry_aspects(spec_a, spec_b)

    return CompatibilityPromptInput(
        person_a=person_a,
        person_b=person_b,
        aspects=aspects,
        relationship_context=report.relationship_context,  # type: ignore[arg-type]
        pair_mode=report.pair_mode,  # type: ignore[arg-type]
    )


async def build_prompt_input_from_report(
    session: AsyncSession,
    report: CompatibilityReport,
) -> CompatibilityPromptInput:
    if report.astro_context and report.astro_context.get("aspects"):
        person_a = person_input_from_snapshot(report.person_a_snapshot)
        person_b = person_input_from_snapshot(report.person_b_snapshot)
        aspects = [
            SynastryAspectInput.model_validate(item)
            for item in report.astro_context["aspects"]
        ]
        return CompatibilityPromptInput(
            person_a=person_a,
            person_b=person_b,
            aspects=aspects,
            relationship_context=report.relationship_context,  # type: ignore[arg-type]
            pair_mode=report.pair_mode,  # type: ignore[arg-type]
        )
    return await _compute_prompt_input_from_snapshots(session, report)


async def build_and_store_synastry(
    session: AsyncSession,
    report_id: uuid.UUID,
) -> CompatibilityReport | None:
    report = await compatibility_crud.get_compatibility_report(session, report_id)
    if report is None:
        logger.warning("Compatibility report missing: %s", report_id)
        return None
    if report.status in {
        ReportStatus.SYNASTRY_READY,
        ReportStatus.TEXT_READY,
        ReportStatus.READY,
    } and report.astro_context:
        return report

    prompt_input = await _compute_prompt_input_from_snapshots(session, report)
    astro_context = {
        "aspects": [aspect.model_dump() for aspect in prompt_input.aspects],
        "relationship_context": report.relationship_context,
        "pair_mode": report.pair_mode,
    }
    await compatibility_crud.mark_report_synastry_ready(session, report, astro_context)
    return report


async def generate_compatibility_llm(
    session: AsyncSession,
    report_id: uuid.UUID,
) -> CompatibilityReport | None:
    settings = get_settings()
    report = await compatibility_crud.get_compatibility_report(session, report_id)
    if report is None:
        logger.warning("Compatibility report missing: %s", report_id)
        return None
    if report.status in {ReportStatus.TEXT_READY, ReportStatus.READY} and report.llm_output:
        return report

    deepseek = get_deepseek_provider(settings)
    if not deepseek.is_configured():
        await compatibility_crud.mark_report_failed(session, report, "deepseek_disabled")
        return None

    try:
        prompt_input = await build_prompt_input_from_report(session, report)
        output, failure = await generate_compatibility_output(prompt_input, deepseek, settings)
        if output is None:
            logger.error(
                "Compatibility LLM failed report=%s reason=%s",
                report_id,
                failure,
            )
            await compatibility_crud.mark_report_failed(session, report, failure or "llm_failed")
            user = await users_crud.get_user_by_id(session, report.owner_user_id)
            if user is not None:
                from astra.services.compatibility_failure_notify import (
                    send_compatibility_failure_notification,
                )

                await send_compatibility_failure_notification(user.telegram_id)
            return None
        await compatibility_crud.mark_report_text_ready(session, report, output.model_dump())
        return report
    except Exception as exc:
        logger.exception("Compatibility LLM failed %s", report_id)
        await compatibility_crud.mark_report_failed(session, report, str(exc))
        return None


async def generate_compatibility_pdf(
    session: AsyncSession,
    report_id: uuid.UUID,
) -> CompatibilityReport | None:
    settings = get_settings()
    report = await compatibility_crud.get_compatibility_report(session, report_id)
    if report is None:
        logger.warning("Compatibility report missing: %s", report_id)
        return None
    if report.status == ReportStatus.READY and report.pdf_path:
        return report
    if not report.llm_output:
        await compatibility_crud.mark_report_failed(session, report, "missing_llm_output")
        return None

    try:
        prompt_input = await build_prompt_input_from_report(session, report)
        output = CompatibilityLlmOutput.model_validate(report.llm_output)
        report_data = llm_output_to_report_data(prompt_input, output)
        out_path = pdf_path_for_report(settings, report)
        generate_synastry_pdf(out_path, report_data)
        await compatibility_crud.mark_report_ready(
            session,
            report,
            llm_output=report.llm_output,
            astro_context=report.astro_context or {},
            pdf_path=str(out_path),
        )
        return report
    except Exception as exc:
        logger.exception("Compatibility PDF failed %s", report_id)
        await compatibility_crud.mark_report_failed(session, report, str(exc))
        return None


async def process_compatibility_report(session: AsyncSession, report_id: uuid.UUID) -> None:
    """Полный цикл (legacy sync helper для тестов и отладки)."""
    report = await build_and_store_synastry(session, report_id)
    if report is None:
        return
    report = await generate_compatibility_llm(session, report_id)
    if report is None:
        return
    report = await generate_compatibility_pdf(session, report_id)
    if report is None:
        return
    await deliver_compatibility_report(session, report_id)


async def enqueue_compatibility_report(
    report_id: uuid.UUID,
    settings: Settings | None = None,
) -> None:
    del settings
    await enqueue_compatibility_pipeline(report_id)


async def request_compatibility_report(
    session: AsyncSession,
    report_id: uuid.UUID,
) -> CompatibilityRequestOutcome:
    report = await compatibility_crud.get_compatibility_report(session, report_id)
    if report is None:
        return CompatibilityRequestOutcome(status=CompatibilityRequestStatus.FAILED)

    status = ReportStatus(report.status)
    if status in COMPATIBILITY_IN_FLIGHT_STATUSES and report.sent_at is None:
        return CompatibilityRequestOutcome(
            status=CompatibilityRequestStatus.IN_PROGRESS,
            report_id=report_id,
        )
    if status == ReportStatus.FAILED:
        return CompatibilityRequestOutcome(
            status=CompatibilityRequestStatus.FAILED,
            report_id=report_id,
        )
    if status == ReportStatus.READY and report.sent_at is not None:
        return CompatibilityRequestOutcome(
            status=CompatibilityRequestStatus.QUEUED,
            report_id=report_id,
        )

    if status == ReportStatus.PENDING:
        await compatibility_crud.mark_report_generating(session, report)
    await resume_compatibility_pipeline(report)
    return CompatibilityRequestOutcome(
        status=CompatibilityRequestStatus.QUEUED,
        report_id=report_id,
    )


@dataclass(frozen=True, slots=True)
class FsmPersonData:
    name: str
    gender: str | None
    birth_date: date
    birth_time: datetime | None
    birth_place: str
    birth_place_id: uuid.UUID | None
    timezone: str


async def snapshot_for_fsm_person(
    session: AsyncSession,
    data: FsmPersonData,
) -> dict:
    tier = 100 if data.birth_time else 66 if data.birth_place_id else 33
    lat, lon, tz = await _coordinates(
        session,
        birth_place_id=data.birth_place_id,
        timezone=data.timezone,
    )
    chart = build_natal_chart_for_birth(
        name=data.name,
        birth_date=data.birth_date,
        birth_time=data.birth_time,
        lat=lat,
        lon=lon,
        timezone=tz,
        accuracy_tier=tier,
    )
    birth_time_iso = data.birth_time.isoformat() if data.birth_time else None
    return {
        "name": data.name,
        "gender": data.gender,
        "birth_date": data.birth_date.isoformat(),
        "birth_time": birth_time_iso,
        "birth_place": data.birth_place,
        "birth_place_id": str(data.birth_place_id) if data.birth_place_id else None,
        "timezone": tz,
        "accuracy_tier": tier,
        "natal": chart_to_natal_dict(chart),
        "chart": chart.model_dump(),
    }


async def snapshot_for_user_profile(session: AsyncSession, profile: Profile) -> dict:
    chart = await chart_for_profile(session, profile)
    snap = snapshot_from_profile(profile, chart)
    snap["chart"] = chart.model_dump()
    return snap


async def create_report_from_fsm(
    session: AsyncSession,
    user: User,
    *,
    relationship_context: RelationshipContext,
    pair_mode: PairMode,
    person_a: FsmPersonData | None,
    person_b: FsmPersonData,
) -> CompatibilityReport:
    if pair_mode == PairMode.ME_PARTNER:
        if user.profile is None:
            raise ValueError("profile required")
        snap_a = await snapshot_for_user_profile(session, user.profile)
        person_a_profile_id = None
    else:
        if person_a is None:
            raise ValueError("person_a required for two_people")
        natal_a = await compatibility_crud.upsert_natal_profile(
            session,
            owner_user_id=user.id,
            label=person_a.name,
            gender=person_a.gender,
            birth_date=person_a.birth_date,
            birth_time=person_a.birth_time,
            birth_place=person_a.birth_place,
            birth_place_id=person_a.birth_place_id,
            timezone=person_a.timezone,
        )
        chart_a = await chart_for_natal_profile(session, natal_a)
        natal_a.chart_data = chart_a.model_dump()
        snap_a = snapshot_from_natal_profile(natal_a, chart_a)
        snap_a["chart"] = chart_a.model_dump()
        person_a_profile_id = natal_a.id

    natal_b = await compatibility_crud.upsert_natal_profile(
        session,
        owner_user_id=user.id,
        label=person_b.name,
        gender=person_b.gender,
        birth_date=person_b.birth_date,
        birth_time=person_b.birth_time,
        birth_place=person_b.birth_place,
        birth_place_id=person_b.birth_place_id,
        timezone=person_b.timezone,
    )
    chart_b = await chart_for_natal_profile(session, natal_b)
    natal_b.chart_data = chart_b.model_dump()
    snap_b = snapshot_from_natal_profile(natal_b, chart_b)
    snap_b["chart"] = chart_b.model_dump()

    title = build_report_title(
        str(snap_a["name"]),
        str(snap_b["name"]),
        relationship_context,
    )
    return await compatibility_crud.create_compatibility_report(
        session,
        owner_user_id=user.id,
        relationship_context=relationship_context.value,
        pair_mode=pair_mode.value,
        person_a_natal_profile_id=person_a_profile_id,
        person_b_natal_profile_id=natal_b.id,
        person_a_snapshot=snap_a,
        person_b_snapshot=snap_b,
        title=title,
    )


async def deliver_compatibility_report(
    session: AsyncSession,
    report_id: uuid.UUID,
    *,
    resend: bool = False,
) -> bool:
    """Отправить готовый PDF в Telegram."""
    report = await compatibility_crud.get_compatibility_report(session, report_id)
    if report is None or report.status != ReportStatus.READY or not report.pdf_path:
        return False
    if report.sent_at is not None and not resend:
        return True

    user = await users_crud.get_user_by_id(session, report.owner_user_id)
    if user is None:
        return False

    pdf_path = Path(report.pdf_path)
    if not pdf_path.is_file():
        await compatibility_crud.mark_report_failed(session, report, "pdf_missing")
        return False

    from astra.workers.telegram_send import send_compatibility_pdf

    await send_compatibility_pdf(
        user.telegram_id,
        pdf_path,
        caption=f"💕 {report.title}",
    )
    await compatibility_crud.mark_report_sent(session, report)
    return True


async def delete_compatibility_report_for_user(
    session: AsyncSession,
    report_id: uuid.UUID,
    owner_user_id: uuid.UUID,
) -> bool:
    """Удалить разбор пользователя: PDF с диска, запись в БД, progress в Redis."""
    report = await compatibility_crud.get_compatibility_report(session, report_id)
    if report is None or report.owner_user_id != owner_user_id:
        return False

    if report.pdf_path:
        pdf_path = Path(report.pdf_path)
        if pdf_path.is_file():
            pdf_path.unlink(missing_ok=True)

    from astra.telegram.progress import clear_progress_message_id, compatibility_job_key
    from astra.users import crud as users_crud

    user = await users_crud.get_user_by_id(session, owner_user_id)
    if user is not None:
        await clear_progress_message_id(owner_user_id, compatibility_job_key(report_id))

    return await compatibility_crud.delete_compatibility_report(session, report_id)
