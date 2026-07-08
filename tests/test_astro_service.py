from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from astra.core.prediction_errors import LlmGenerationError
from astra.predictions.status import PredictionStatus
from astra.services.astro_service import generate_prediction_text_only

_TARGET = date(2026, 7, 8)

_V2_CONTEXT = {
    "schema_version": 2,
    "date": _TARGET.isoformat(),
    "accuracy_tier": 100,
    "has_time": True,
    "big_three": {"sun": "Лев", "moon": "Дева", "asc": None},
}

_V1_CONTEXT = {
    "date": _TARGET.isoformat(),
    "accuracy_tier": 100,
    "natal": {"sun": "Лев"},
    "transits": [],
}


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4())


def _profile() -> SimpleNamespace:
    return SimpleNamespace(display_name="Аид")


def _stored_prediction(context: dict | None) -> SimpleNamespace:
    return SimpleNamespace(astro_context=context)


@pytest.mark.anyio
async def test_text_only_raises_when_context_missing() -> None:
    session = AsyncMock()
    with patch(
        "astra.services.astro_service.predictions_crud.get_prediction_for_date",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with pytest.raises(LlmGenerationError) as exc_info:
            await generate_prediction_text_only(
                session, _user(), _profile(), _TARGET, settings=SimpleNamespace()
            )

    assert exc_info.value.reason == "missing_context"


@pytest.mark.anyio
async def test_text_only_raises_when_provider_disabled() -> None:
    session = AsyncMock()
    with patch(
        "astra.services.astro_service.predictions_crud.get_prediction_for_date",
        new_callable=AsyncMock,
        return_value=_stored_prediction(_V2_CONTEXT),
    ):
        with patch(
            "astra.services.astro_service.daily_provider_enabled",
            return_value=False,
        ):
            with pytest.raises(LlmGenerationError) as exc_info:
                await generate_prediction_text_only(
                    session, _user(), _profile(), _TARGET, settings=SimpleNamespace()
                )

    assert exc_info.value.reason == "disabled"


@pytest.mark.anyio
async def test_text_only_generates_v4_and_updates_prediction() -> None:
    session = AsyncMock()
    stored = _stored_prediction(_V2_CONTEXT)
    expected_text = "Что важнее?\n\nСегодня день про баланс.\n\nСделай паузу — или реши."
    updated = SimpleNamespace(text=expected_text)

    with patch(
        "astra.services.astro_service.predictions_crud.get_prediction_for_date",
        new_callable=AsyncMock,
        return_value=stored,
    ):
        with patch(
            "astra.services.astro_service.daily_provider_enabled",
            return_value=True,
        ):
            with patch(
                "astra.services.astro_service.generate_daily_body_v4",
                new_callable=AsyncMock,
                return_value=(expected_text, ""),
            ) as generate:
                with patch(
                    "astra.services.astro_service.predictions_crud.update_prediction",
                    new_callable=AsyncMock,
                    return_value=updated,
                ) as update:
                    result = await generate_prediction_text_only(
                        session, _user(), _profile(), _TARGET, settings=SimpleNamespace()
                    )

    assert result is updated
    generate.assert_awaited_once()
    ctx_arg = generate.await_args.args[0]
    assert ctx_arg.schema_version == 2
    assert ctx_arg.big_three["sun"] == "Лев"
    update.assert_awaited_once_with(
        session,
        stored,
        text=expected_text,
        status=PredictionStatus.TEXT_READY,
    )


@pytest.mark.anyio
async def test_text_only_raises_with_reason_when_v4_empty() -> None:
    session = AsyncMock()
    with patch(
        "astra.services.astro_service.predictions_crud.get_prediction_for_date",
        new_callable=AsyncMock,
        return_value=_stored_prediction(_V2_CONTEXT),
    ):
        with patch(
            "astra.services.astro_service.daily_provider_enabled",
            return_value=True,
        ):
            with patch(
                "astra.services.astro_service.generate_daily_body_v4",
                new_callable=AsyncMock,
                return_value=(None, "timeout"),
            ):
                with pytest.raises(LlmGenerationError) as exc_info:
                    await generate_prediction_text_only(
                        session, _user(), _profile(), _TARGET, settings=SimpleNamespace()
                    )

    assert exc_info.value.reason == "timeout"


@pytest.mark.anyio
async def test_text_only_rejects_legacy_v1_context() -> None:
    session = AsyncMock()
    with patch(
        "astra.services.astro_service.predictions_crud.get_prediction_for_date",
        new_callable=AsyncMock,
        return_value=_stored_prediction(_V1_CONTEXT),
    ):
        with pytest.raises(LlmGenerationError) as exc_info:
            await generate_prediction_text_only(
                session, _user(), _profile(), _TARGET, settings=SimpleNamespace()
            )

    assert exc_info.value.reason == "legacy_context"
