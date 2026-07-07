from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from astra.astro.calculator import build_full_natal_chart, build_natal_chart
from astra.astro.crud import chart_data_from_row, get_natal_chart, upsert_natal_chart
from astra.astro.schemas import AstroContext, NatalChartData, TransitAspect
from astra.astro.daily_context import DailyContextV2, build_daily_context_v2
from astra.astro.transits import build_daily_context
from astra.core.config import Settings, get_settings
from astra.core.prediction_errors import LlmGenerationError
from astra.llm.daily_llm import daily_provider_enabled, generate_daily_body_v4
from astra.llm.ollama import generate_prediction_body as llm_generate_body
from astra.llm.prompts.astrid import QuestionArchetype, pick_question_archetype
from astra.places import crud as places_crud
from astra.predictions import crud as predictions_crud
from astra.predictions.models import Prediction
from astra.predictions.status import PredictionStatus
from astra.users import crud as users_crud
from astra.users.models import Profile, User


async def _birth_coordinates(session: AsyncSession, profile: Profile) -> tuple[float, float, str]:
    if profile.birth_place_id:
        place = await places_crud.get_place_by_id(session, profile.birth_place_id)
        if place is not None:
            return float(place.latitude), float(place.longitude), place.timezone
    return 55.75, 37.62, profile.timezone


def _profile_snapshot(profile: Profile) -> dict[str, str | None]:
    birth_time = profile.birth_time.isoformat() if profile.birth_time else None
    return {
        "birth_date": profile.birth_date.isoformat(),
        "birth_time": birth_time,
        "birth_place": profile.birth_place,
        "birth_place_id": str(profile.birth_place_id) if profile.birth_place_id else None,
        "display_name": profile.display_name,
    }


async def compute_and_store_natal_chart(
    session: AsyncSession,
    user: User,
    profile: Profile,
) -> NatalChartData:
    lat, lon, tz = await _birth_coordinates(session, profile)
    chart = build_natal_chart(profile, lat=lat, lon=lon, timezone=tz)
    chart.profile_snapshot = _profile_snapshot(profile)
    await upsert_natal_chart(session, user.id, chart)
    return chart


async def refresh_natal_chart_for_profile(
    session: AsyncSession,
    profile: Profile,
) -> NatalChartData | None:
    """Пересчитать натал по актуальному профилю (после flush)."""
    await session.refresh(profile)
    user = await users_crud.get_user_by_id(session, profile.user_id)
    if user is None:
        return None
    return await compute_and_store_natal_chart(session, user, profile)


async def refresh_natal_chart(session: AsyncSession, user_id: UUID) -> NatalChartData | None:
    user = await users_crud.get_user_by_id(session, user_id)
    if user is None or user.profile is None:
        return None
    return await refresh_natal_chart_for_profile(session, user.profile)


async def ensure_natal_chart(
    session: AsyncSession,
    user: User,
    profile: Profile,
) -> NatalChartData:
    return await compute_and_store_natal_chart(session, user, profile)


async def build_context_for_date(
    session: AsyncSession,
    user: User,
    profile: Profile,
    target: date,
) -> tuple[AstroContext, NatalChartData]:
    chart = await ensure_natal_chart(session, user, profile)
    ctx = build_daily_context(profile, chart, target)
    return ctx, chart


def build_prediction_astro_context(
    ctx: AstroContext,
    archetype: QuestionArchetype,
) -> dict:
    """Контекст для predictions.astro_context: транзиты + метаданные генерации."""
    payload = ctx.model_dump_json_safe()
    payload["question_archetype_id"] = archetype.id
    return payload


def astro_context_from_stored(payload: dict) -> AstroContext:
    data = {key: value for key, value in payload.items() if key != "question_archetype_id"}
    return AstroContext(
        date=date.fromisoformat(data["date"]),
        accuracy_tier=data["accuracy_tier"],
        natal=data["natal"],
        transits=[TransitAspect.model_validate(item) for item in data["transits"]],
        moon_phase=data.get("moon_phase"),
    )


async def load_natal_chart_data(session: AsyncSession, user_id: UUID) -> NatalChartData:
    row = await get_natal_chart(session, user_id)
    if row is None:
        raise LlmGenerationError("missing_natal_chart")
    return chart_data_from_row(row)


async def build_full_chart_for_user(
    session: AsyncSession,
    user: User,
    profile: Profile,
):
    """FullNatalChart по профилю (координаты из места рождения)."""
    lat, lon, tz = await _birth_coordinates(session, profile)
    return build_full_natal_chart(
        name=profile.display_name,
        birth_date=profile.birth_date,
        birth_time=profile.birth_time,
        lat=lat,
        lon=lon,
        timezone=tz,
    )


async def build_and_store_daily_context(
    session: AsyncSession,
    user: User,
    profile: Profile,
    target: date,
) -> Prediction:
    chart = await load_natal_chart_data(session, user.id)
    full_chart = await build_full_chart_for_user(session, user, profile)
    archetype = pick_question_archetype(user.id, target)
    ctx = build_daily_context_v2(
        full_chart,
        target,
        accuracy_tier=chart.accuracy_tier,
        question_archetype_id=archetype.id,
    )
    return await predictions_crud.upsert_context_draft(
        session,
        user_id=user.id,
        prediction_date=target,
        astro_context=ctx.model_dump(mode="json"),
    )


async def generate_prediction_text_only(
    session: AsyncSession,
    user: User,
    profile: Profile,
    target: date,
    settings: Settings | None = None,
) -> Prediction:
    cfg = settings or get_settings()

    prediction = await predictions_crud.get_prediction_for_date(session, user.id, target)
    if prediction is None or prediction.astro_context is None:
        raise LlmGenerationError("missing_context")

    stored = prediction.astro_context
    if stored.get("schema_version") == 2:
        if not daily_provider_enabled(cfg):
            raise LlmGenerationError("disabled")
        ctx_v2 = DailyContextV2.model_validate(stored)
        body, failure_reason = await generate_daily_body_v4(ctx_v2, cfg)
    else:
        # legacy-контекст v1 (черновики до раската v4)
        if not cfg.ollama_enabled:
            raise LlmGenerationError("disabled")
        chart = await load_natal_chart_data(session, user.id)
        ctx = astro_context_from_stored(stored)
        archetype = pick_question_archetype(user.id, target)
        body, failure_reason = await llm_generate_body(
            ctx,
            profile,
            chart,
            cfg,
            archetype=archetype,
        )
    if not body:
        raise LlmGenerationError(failure_reason or "empty_response")
    return await predictions_crud.update_prediction(
        session,
        prediction,
        text=body,
        status=PredictionStatus.TEXT_READY,
    )


async def generate_prediction_body(
    session: AsyncSession,
    user: User,
    profile: Profile,
    target: date,
    settings: Settings | None = None,
) -> tuple[str, dict]:
    cfg = settings or get_settings()
    ctx, chart = await build_context_for_date(session, user, profile, target)
    if not cfg.ollama_enabled:
        raise LlmGenerationError("disabled")

    archetype = pick_question_archetype(user.id, target)
    body, failure_reason = await llm_generate_body(
        ctx,
        profile,
        chart,
        cfg,
        archetype=archetype,
    )
    if not body:
        raise LlmGenerationError(failure_reason or "empty_response")
    return body, build_prediction_astro_context(ctx, archetype)


async def create_or_update_prediction(
    session: AsyncSession,
    user_id: UUID,
    target: date,
    body: str,
    astro_context: dict,
) -> Prediction:
    existing = await predictions_crud.get_prediction_for_date(session, user_id, target)
    if existing:
        return await predictions_crud.update_prediction(
            session,
            existing,
            text=body,
            astro_context=astro_context,
            status=PredictionStatus.TEXT_READY,
        )
    return await predictions_crud.create_prediction(
        session,
        user_id=user_id,
        prediction_date=target,
        text=body,
        astro_context=astro_context,
        status=PredictionStatus.TEXT_READY,
    )


async def generate_daily_prediction(
    session: AsyncSession,
    user: User,
    profile: Profile,
    target: date | None = None,
    settings: Settings | None = None,
) -> Prediction:
    day = target or date.today()
    body, ctx = await generate_prediction_body(session, user, profile, day, settings)
    return await create_or_update_prediction(session, user.id, day, body, ctx)

