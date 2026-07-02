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
    RELATIONSHIP_LABELS,
    PairMode,
    RelationshipContext,
    ReportStatus,
)
from astra.compatibility.models import CompatibilityReport, NatalProfile
from astra.core.config import Settings, get_settings
from astra.llm.compatibility_generate import generate_compatibility_output
from astra.llm.factory import get_deepseek_provider
from astra.llm.schemas.compatibility import CompatibilityPersonInput, CompatibilityPromptInput
from astra.places import crud as places_crud
from astra.reports.synastry import generate_synastry_pdf
from astra.reports.synastry.mapper import llm_output_to_report_data
from astra.users import crud as users_crud
from astra.users.gender import GENDER_FEMALE, GENDER_MALE
from astra.users.models import Profile, User

logger = logging.getLogger(__name__)

COMPATIBILITY_IN_PROGRESS_TEXT = (
    "Готовлю PDF-разбор совместимости ✨\n"
    "Пришлю сюда через пару минут."
)


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


def pdf_filename(report_id: uuid.UUID) -> str:
    return f"compatibility-{report_id}.pdf"


def pdf_path_for_report(settings: Settings, report_id: uuid.UUID) -> Path:
    base = Path(settings.compatibility_pdf_dir)
    base.mkdir(parents=True, exist_ok=True)
    return base / pdf_filename(report_id)


async def build_prompt_input_from_report(
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


async def process_compatibility_report(session: AsyncSession, report_id: uuid.UUID) -> None:
    """Полный цикл генерации PDF (вызывается из worker)."""
    settings = get_settings()
    report = await compatibility_crud.get_compatibility_report(session, report_id)
    if report is None:
        logger.warning("Compatibility report missing: %s", report_id)
        return
    if report.status == ReportStatus.READY and report.pdf_path:
        return

    await compatibility_crud.mark_report_generating(session, report)

    deepseek = get_deepseek_provider(settings)
    if not deepseek.is_configured():
        await compatibility_crud.mark_report_failed(session, report, "deepseek_disabled")
        return

    try:
        prompt_input = await build_prompt_input_from_report(session, report)
        output, failure = await generate_compatibility_output(prompt_input, deepseek, settings)
        if output is None:
            await compatibility_crud.mark_report_failed(session, report, failure or "llm_failed")
            return

        report_data = llm_output_to_report_data(prompt_input, output)
        out_path = pdf_path_for_report(settings, report.id)
        generate_synastry_pdf(out_path, report_data)

        astro_context = {
            "aspects": [a.model_dump() for a in prompt_input.aspects],
            "relationship_context": report.relationship_context,
            "pair_mode": report.pair_mode,
        }
        await compatibility_crud.mark_report_ready(
            session,
            report,
            llm_output=output.model_dump(),
            astro_context=astro_context,
            pdf_path=str(out_path),
        )
    except Exception as exc:
        logger.exception("Compatibility report failed %s", report_id)
        await compatibility_crud.mark_report_failed(session, report, str(exc))


async def enqueue_compatibility_report(
    report_id: uuid.UUID,
    settings: Settings | None = None,
) -> None:
    from astra.messaging.publisher import publish_compatibility_generate

    await publish_compatibility_generate(report_id, settings)


async def request_compatibility_report(
    session: AsyncSession,
    report_id: uuid.UUID,
    *,
    allow_async: bool = True,
) -> CompatibilityRequestOutcome:
    settings = get_settings()
    report = await compatibility_crud.get_compatibility_report(session, report_id)
    if report is None:
        return CompatibilityRequestOutcome(status=CompatibilityRequestStatus.FAILED)

    if report.status == ReportStatus.GENERATING:
        return CompatibilityRequestOutcome(
            status=CompatibilityRequestStatus.IN_PROGRESS,
            report_id=report_id,
        )
    if report.status == ReportStatus.FAILED:
        return CompatibilityRequestOutcome(
            status=CompatibilityRequestStatus.FAILED,
            report_id=report_id,
        )
    if report.status == ReportStatus.READY:
        return CompatibilityRequestOutcome(
            status=CompatibilityRequestStatus.QUEUED,
            report_id=report_id,
        )

    if allow_async and settings.rabbitmq_enabled:
        await enqueue_compatibility_report(report_id, settings)
        return CompatibilityRequestOutcome(
            status=CompatibilityRequestStatus.QUEUED,
            report_id=report_id,
        )

    await process_compatibility_report(session, report_id)
    await deliver_compatibility_report(session, report_id)
    refreshed = await compatibility_crud.get_compatibility_report(session, report_id)
    if refreshed is None or refreshed.status == ReportStatus.FAILED:
        return CompatibilityRequestOutcome(status=CompatibilityRequestStatus.FAILED, report_id=report_id)
    return CompatibilityRequestOutcome(status=CompatibilityRequestStatus.QUEUED, report_id=report_id)


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
    if gender == GENDER_MALE:
        return "мужчина"
    if gender == GENDER_FEMALE:
        return "женщина"
    return "не указан"
