from datetime import date
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from astra.predictions.status import PredictionStatus
from astra.services.prediction_pipeline import (
    enqueue_prediction_pipeline,
    resume_prediction_pipeline,
)


@pytest.mark.asyncio
async def test_enqueue_prediction_pipeline_starts_with_natal_when_missing() -> None:
    user_id = uuid4()
    target = date(2026, 7, 2)
    session = AsyncMock()

    with (
        patch(
            "astra.services.prediction_pipeline.astro_crud.get_natal_chart",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "astra.services.prediction_pipeline.publish_natal_chart",
            new=AsyncMock(),
        ) as publish_natal,
        patch(
            "astra.services.prediction_pipeline.publish_daily_context_build",
            new=AsyncMock(),
        ) as publish_context,
    ):
        await enqueue_prediction_pipeline(session, user_id, target)

    publish_natal.assert_awaited_once_with(user_id, target)
    publish_context.assert_not_awaited()


@pytest.mark.asyncio
async def test_enqueue_prediction_pipeline_skips_natal_when_present() -> None:
    user_id = uuid4()
    target = date(2026, 7, 2)
    session = AsyncMock()

    with (
        patch(
            "astra.services.prediction_pipeline.astro_crud.get_natal_chart",
            new=AsyncMock(return_value=object()),
        ),
        patch(
            "astra.services.prediction_pipeline.publish_natal_chart",
            new=AsyncMock(),
        ) as publish_natal,
        patch(
            "astra.services.prediction_pipeline.publish_daily_context_build",
            new=AsyncMock(),
        ) as publish_context,
    ):
        await enqueue_prediction_pipeline(session, user_id, target)

    publish_natal.assert_not_awaited()
    publish_context.assert_awaited_once_with(user_id, target)


@pytest.mark.asyncio
async def test_resume_prediction_pipeline_from_context_ready() -> None:
    user_id = uuid4()
    target = date(2026, 7, 2)
    session = AsyncMock()
    prediction = AsyncMock(status=PredictionStatus.CONTEXT_READY.value)

    with (
        patch(
            "astra.services.prediction_pipeline.publish_prediction_generate",
            new=AsyncMock(),
        ) as publish_generate,
        patch(
            "astra.services.prediction_pipeline.publish_prediction_send",
            new=AsyncMock(),
        ) as publish_send,
    ):
        await resume_prediction_pipeline(session, user_id, target, prediction)

    publish_generate.assert_awaited_once_with(user_id, target)
    publish_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_prediction_pipeline_from_text_ready() -> None:
    user_id = uuid4()
    target = date(2026, 7, 2)
    session = AsyncMock()
    prediction = AsyncMock(status=PredictionStatus.TEXT_READY.value)

    with (
        patch(
            "astra.services.prediction_pipeline.publish_prediction_generate",
            new=AsyncMock(),
        ) as publish_generate,
        patch(
            "astra.services.prediction_pipeline.publish_prediction_send",
            new=AsyncMock(),
        ) as publish_send,
    ):
        await resume_prediction_pipeline(session, user_id, target, prediction)

    publish_generate.assert_not_awaited()
    publish_send.assert_awaited_once_with(user_id, target)
