import re
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from astra.core.prediction_errors import LlmGenerationError
from astra.llm.prompts.astrid import sanitize_prediction_output, validate_prediction_output
from astra.llm.prompts.astrid_checklist import checklist_passed, run_v3_checklist
from astra.services.prediction_generation import generate_daily_prediction_resilient

_VALID_BODY = (
    "Aidamir, сегодня ты можешь почувствовать баланс между делами и желаниями. "
    "Обрати внимание на разговоры с близкими — слова могут звучать острее, чем ты думаешь. "
    "Это хороший момент прояснить свои намерения и выбрать, что действительно важно. "
    "Постарайся не смешивать срочное с главным."
)


def _valid_raw(
    *,
    question: str = "Что важнее — быть правым или быть близким?",
    body: str = _VALID_BODY,
    advice: str = "Сделай паузу перед разговором, который давно откладываешь.",
) -> str:
    return f"{question}\n\n{body}\n\n{advice}"


def test_v3_checklist_passes_on_valid_output() -> None:
    text = sanitize_prediction_output(_valid_raw())
    checks = run_v3_checklist(text, "Aidamir")
    assert checklist_passed(checks)


def test_v3_checklist_fails_without_name() -> None:
    text = sanitize_prediction_output(
        _valid_raw(body=_VALID_BODY.replace("Aidamir,", "Марина,")),
    )
    checks = run_v3_checklist(text, "Aidamir")
    assert not checklist_passed(checks)
    assert any(item.name == "name_in_first_sentence" and not item.passed for item in checks)


def test_v3_checklist_fails_legacy_format() -> None:
    text = _valid_raw() + "\n\n🔢 Число дня: 7"
    checks = run_v3_checklist(text, "Aidamir")
    assert not checklist_passed(checks)


def test_validate_rejects_missing_name_for_retry_path() -> None:
    text = sanitize_prediction_output(_valid_raw(body=_VALID_BODY.replace("Aidamir,", "Марина,")))
    assert validate_prediction_output(text, "Aidamir") == "missing_name"


@pytest.mark.anyio
async def test_resilient_generation_retries_on_validation_failure() -> None:
    session = AsyncMock()
    user = type("U", (), {"id": uuid4(), "telegram_id": 123})()
    profile = type("P", (), {})()
    target = __import__("datetime").date(2026, 6, 14)
    prediction = AsyncMock()

    call_count = 0

    async def _generate(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise LlmGenerationError("missing_name")
        return prediction

    with patch(
        "astra.services.prediction_generation.generate_daily_prediction",
        side_effect=_generate,
    ):
        with patch(
            "astra.services.prediction_generation.maybe_send_delayed_notification",
            new_callable=AsyncMock,
        ):
            with patch("astra.services.prediction_generation.asyncio.sleep", new_callable=AsyncMock):
                result = await generate_daily_prediction_resilient(
                    session,
                    user,
                    profile,
                    target=target,
                )

    assert result is prediction
    assert call_count == 2


def test_push_preview_under_iphone_limit() -> None:
    text = sanitize_prediction_output(_valid_raw())
    question = text.split("\n\n", 1)[0]
    assert len(question) <= 110
