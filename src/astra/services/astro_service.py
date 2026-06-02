from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from astra.astro.calculator import build_natal_chart
from astra.astro.crud import upsert_natal_chart
from astra.astro.schemas import AstroContext, NatalChartData
from astra.astro.templates import body_from_context
from astra.astro.transits import build_daily_context
from astra.core.config import Settings, get_settings
from astra.llm.ollama import generate_prediction_body as llm_generate_body
from astra.places import crud as places_crud
from astra.predictions import crud as predictions_crud
from astra.predictions.models import Prediction
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


async def generate_prediction_body(
    session: AsyncSession,
    user: User,
    profile: Profile,
    target: date,
    settings: Settings | None = None,
) -> tuple[str, dict]:
    cfg = settings or get_settings()
    ctx, chart = await build_context_for_date(session, user, profile, target)
    body: str | None = None
    if cfg.ollama_enabled:
        body = await llm_generate_body(ctx, profile, chart, cfg)
    if not body:
        body = body_from_context(ctx)
    return body, ctx.model_dump_json_safe()


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
        )
    return await predictions_crud.create_prediction(
        session,
        user_id=user_id,
        prediction_date=target,
        text=body,
        astro_context=astro_context,
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

