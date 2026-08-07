from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from astra.astro.calculator import build_full_natal_chart, build_natal_chart
from astra.astro.crud import chart_data_from_row, get_natal_chart, upsert_natal_chart
from astra.astro.schemas import NatalChartData
from astra.astro.daily_context import DailyContextV2, build_daily_context_v2
from astra.core.config import Settings, get_settings
from astra.core.prediction_errors import LlmGenerationError
from astra.llm.daily_llm import daily_provider_enabled, generate_daily_body_v4
from astra.llm.prompts.astrid import pick_question_archetype
from astra.places import crud as places_crud
from astra.predictions import crud as predictions_crud
from astra.predictions.models import Prediction
from astra.predictions.status import PredictionStatus
from astra.users import crud as users_crud
from astra.users.birth_data import BirthDataMissing, BirthField
from astra.users.models import Profile, User


async def birth_coordinates(session: AsyncSession, profile: Profile) -> tuple[float, float, str]:
    """Координаты места рождения.

    Место не разрешилось в справочник — отдаём Москву. Всё, что зависит от
    координат (асцендент, MC, дома), при таком fallback показывать нельзя:
    проверять надо `profile.birth_place_id`, а не процент заполненности.
    """
    if profile.birth_place_id:
        place = await places_crud.get_place_by_id(session, profile.birth_place_id)
        if place is not None:
            return float(place.latitude), float(place.longitude), place.timezone
    return 55.75, 37.62, profile.timezone


def _profile_snapshot(profile: Profile) -> dict[str, str | None]:
    birth_time = profile.birth_time.isoformat() if profile.birth_time else None
    return {
        "birth_date": profile.birth_date.isoformat() if profile.birth_date else None,
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
    lat, lon, tz = await birth_coordinates(session, profile)
    chart = build_natal_chart(profile, lat=lat, lon=lon, timezone=tz)
    chart.profile_snapshot = _profile_snapshot(profile)
    await upsert_natal_chart(session, user.id, chart)
    return chart


async def refresh_natal_chart_for_profile(
    session: AsyncSession,
    profile: Profile,
) -> NatalChartData | None:
    """Пересчитать натал по актуальному профилю (после flush).

    None — считать нечего. Профиль без даты рождения это нормальное
    состояние (короткий онбординг), и пытаться строить по нему карту, чтобы
    поймать исключение, значило бы писать в лог ошибку на каждую правку
    имени или пола.
    """
    await session.refresh(profile)
    if profile.birth_date is None:
        return None
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
    if profile.birth_date is None:
        raise BirthDataMissing((BirthField.DATE,))
    lat, lon, tz = await birth_coordinates(session, profile)
    return build_full_natal_chart(
        name=profile.display_name,
        birth_date=profile.birth_date,
        birth_time=profile.birth_time,
        lat=lat,
        lon=lon,
        timezone=tz,
    )


def _zodiac_context_payload(chart: NatalChartData, target: date) -> dict:
    """Лёгкий контекст общего тарифа: только знак Солнца."""
    return {
        "schema_version": "zodiac",
        "date": target.isoformat(),
        "sign": chart.sun_sign,
        "accuracy_tier": chart.accuracy_tier,
    }


async def build_and_store_daily_context(
    session: AsyncSession,
    user: User,
    profile: Profile,
    target: date,
) -> Prediction:
    cfg = get_settings()
    chart = await load_natal_chart_data(session, user.id)
    if not cfg.personal_predictions_enabled:
        return await predictions_crud.upsert_context_draft(
            session,
            user_id=user.id,
            prediction_date=target,
            astro_context=_zodiac_context_payload(chart, target),
        )
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
    if stored.get("schema_version") == "zodiac":
        from astra.predictions.zodiac_daily import get_or_generate_zodiac_daily

        sign = str(stored.get("sign") or "")
        row = await get_or_generate_zodiac_daily(session, sign, target, cfg)
        if row is None:
            raise LlmGenerationError("zodiac_generation_failed")
        payload = dict(stored)
        payload["moon_note"] = row.moon_note
        prediction.astro_context = payload
        return await predictions_crud.update_prediction(
            session,
            prediction,
            text=row.text,
            status=PredictionStatus.TEXT_READY,
        )
    if stored.get("schema_version") != 2:
        # legacy-контекст v1: генерировался только удалённой локальной LLM
        raise LlmGenerationError("legacy_context")
    if not daily_provider_enabled(cfg):
        raise LlmGenerationError("disabled")
    ctx_v2 = DailyContextV2.model_validate(stored)
    body, failure_reason = await generate_daily_body_v4(ctx_v2, cfg)
    if not body:
        raise LlmGenerationError(failure_reason or "empty_response")
    return await predictions_crud.update_prediction(
        session,
        prediction,
        text=body,
        status=PredictionStatus.TEXT_READY,
    )

