from datetime import date
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from astra.core.prediction_errors import LlmGenerationError, report_prediction_generation_failure
from astra.services.prediction_generation import (
    PREDICTION_DELAYED_NOTIFY_SEC,
    PREDICTION_MAX_ATTEMPTS,
    generate_daily_prediction_resilient,
)


def test_llm_generation_error_human_message() -> None:
    err = LlmGenerationError("timeout")
    assert str(err) == "Предсказание: таймаут Ollama"


def test_report_prediction_generation_failure_final_message() -> None:
    user_id = uuid4()
    with patch("astra.core.prediction_errors.sentry_sdk.is_initialized", return_value=True):
        with patch("astra.core.prediction_errors.sentry_sdk.push_scope") as push_scope:
            scope = push_scope.return_value.__enter__.return_value
            with patch("astra.core.prediction_errors.sentry_sdk.capture_message") as capture:
                report_prediction_generation_failure(
                    user_id=user_id,
                    prediction_date=date(2026, 6, 14),
                    reason="timeout",
                    attempts=5,
                    elapsed_sec=130.5,
                    final=True,
                )

    capture.assert_called_once()
    message, = capture.call_args[0]
    assert message == "Предсказание: таймаут Ollama после 5 попыток"
    assert capture.call_args.kwargs["level"] == "error"
    scope.set_tag.assert_any_call("prediction_failure", "true")
    scope.set_tag.assert_any_call("failure_reason", "timeout")


@pytest.mark.anyio
async def test_generate_daily_prediction_resilient_success_after_retry() -> None:
    user = AsyncMock()
    user.id = uuid4()
    user.telegram_id = 123
    profile = AsyncMock()
    session = AsyncMock()
    prediction = AsyncMock()

    side_effects = [
        LlmGenerationError("timeout"),
        prediction,
    ]

    with patch(
        "astra.services.prediction_generation.generate_daily_prediction",
        side_effect=side_effects,
    ) as generate:
        with patch(
            "astra.services.prediction_generation.maybe_send_delayed_notification",
            new_callable=AsyncMock,
        ) as delayed:
            with patch("astra.services.prediction_generation.asyncio.sleep", new_callable=AsyncMock):
                result = await generate_daily_prediction_resilient(
                    session,
                    user,
                    profile,
                    date(2026, 6, 14),
                )

    assert result is prediction
    assert generate.call_count == 2
    delayed.assert_not_called()


@pytest.mark.anyio
async def test_generate_daily_prediction_resilient_sends_delayed_notice() -> None:
    user = AsyncMock()
    user.id = uuid4()
    user.telegram_id = 123
    profile = AsyncMock()
    session = AsyncMock()

    async def slow_fail(*_args, **_kwargs):
        raise LlmGenerationError("timeout")

    tick = 0

    def monotonic() -> float:
        nonlocal tick
        tick += 1
        if tick == 1:
            return 0.0
        if tick == 2:
            return float(PREDICTION_DELAYED_NOTIFY_SEC + 1)
        return 300.0

    with patch(
        "astra.services.prediction_generation.PREDICTION_MAX_ATTEMPTS",
        2,
    ):
        with patch(
            "astra.services.prediction_generation.generate_daily_prediction",
            side_effect=slow_fail,
        ):
            with patch(
                "astra.services.prediction_generation.time.monotonic",
                side_effect=monotonic,
            ):
                with patch(
                    "astra.services.prediction_generation.maybe_send_delayed_notification",
                    new_callable=AsyncMock,
                ) as delayed:
                    with patch(
                        "astra.services.prediction_generation.asyncio.sleep",
                        new_callable=AsyncMock,
                    ):
                        with patch(
                            "astra.services.prediction_generation.send_final_failure_notification",
                            new_callable=AsyncMock,
                        ):
                            with patch(
                                "astra.services.prediction_generation.clear_prediction_pending",
                                new_callable=AsyncMock,
                            ):
                                result = await generate_daily_prediction_resilient(
                                    session,
                                    user,
                                    profile,
                                    date(2026, 6, 14),
                                )

    assert result is None
    delayed.assert_called_with(user.id, user.telegram_id, date(2026, 6, 14))


@pytest.mark.anyio
async def test_generate_daily_prediction_resilient_final_failure() -> None:
    user = AsyncMock()
    user.id = uuid4()
    user.telegram_id = 456
    profile = AsyncMock()
    session = AsyncMock()

    with patch(
        "astra.services.prediction_generation.generate_daily_prediction",
        side_effect=LlmGenerationError("connection"),
    ):
        with patch(
            "astra.services.prediction_generation.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            with patch(
                "astra.services.prediction_generation.send_final_failure_notification",
                new_callable=AsyncMock,
            ) as failure_notify:
                with patch(
                    "astra.services.prediction_generation.clear_prediction_pending",
                    new_callable=AsyncMock,
                ) as clear_pending:
                    with patch(
                        "astra.services.prediction_generation.report_prediction_generation_failure",
                    ) as report:
                        result = await generate_daily_prediction_resilient(
                            session,
                            user,
                            profile,
                            date(2026, 6, 14),
                        )

    assert result is None
    assert report.call_count == PREDICTION_MAX_ATTEMPTS
    failure_notify.assert_called_once_with(user.telegram_id)
    clear_pending.assert_called_once_with(user.id, date(2026, 6, 14))
