from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from astra.core.prediction_errors import LlmGenerationError
from astra.llm.prompts.astrid import pick_question_archetype
from astra.services.astro_service import (
    build_prediction_astro_context,
    generate_prediction_body,
)


@pytest.mark.anyio
async def test_generate_prediction_body_raises_when_ollama_disabled() -> None:
    session = AsyncMock()
    user = SimpleNamespace(id=uuid4())
    profile = SimpleNamespace(display_name="Аид")
    chart = SimpleNamespace()
    ctx = SimpleNamespace(model_dump_json_safe=lambda: {})

    with patch(
        "astra.services.astro_service.build_context_for_date",
        new_callable=AsyncMock,
        return_value=(ctx, chart),
    ):
        with pytest.raises(LlmGenerationError) as exc_info:
            await generate_prediction_body(
                session,
                user,
                profile,
                date(2026, 6, 14),
                settings=SimpleNamespace(ollama_enabled=False),
            )

    assert exc_info.value.reason == "disabled"


@pytest.mark.anyio
async def test_generate_prediction_body_raises_when_llm_empty() -> None:
    session = AsyncMock()
    user = SimpleNamespace(id=uuid4())
    profile = SimpleNamespace(
        birth_place_id=None,
        timezone="Europe/Moscow",
        birth_date=date(1990, 3, 15),
        birth_time=None,
        birth_place="Москва",
        display_name="Аид",
    )
    chart = SimpleNamespace(
        accuracy_tier=100,
        sun_sign="Водолей",
        moon_sign="Дева",
        asc_sign="Овен",
        timezone="Europe/Moscow",
    )
    ctx = SimpleNamespace(date=date(2026, 6, 14), model_dump_json_safe=lambda: {})

    with patch("astra.services.astro_service.get_settings") as settings:
        settings.return_value.ollama_enabled = True
        with patch(
            "astra.services.astro_service.build_context_for_date",
            new_callable=AsyncMock,
            return_value=(ctx, chart),
        ):
            with patch(
                "astra.services.astro_service.llm_generate_body",
                new_callable=AsyncMock,
                return_value=(None, "timeout"),
            ):
                with pytest.raises(LlmGenerationError) as exc_info:
                    await generate_prediction_body(session, user, profile, date(2026, 6, 14))

    assert exc_info.value.reason == "timeout"


@pytest.mark.anyio
async def test_generate_prediction_body_passes_archetype_and_saves_context() -> None:
    session = AsyncMock()
    user_id = uuid4()
    user = SimpleNamespace(id=user_id)
    profile = SimpleNamespace(display_name="Аид")
    chart = SimpleNamespace()
    target = date(2026, 6, 14)
    archetype = pick_question_archetype(user_id, target)
    ctx = SimpleNamespace(
        date=target,
        model_dump_json_safe=lambda: {"date": target.isoformat(), "transits": []},
    )
    expected_text = "Что важнее — быть правым или быть близким?\n\nАида, сегодня…\n\nОтдохни."

    with patch("astra.services.astro_service.get_settings") as settings:
        settings.return_value.ollama_enabled = True
        with patch(
            "astra.services.astro_service.build_context_for_date",
            new_callable=AsyncMock,
            return_value=(ctx, chart),
        ):
            with patch(
                "astra.services.astro_service.llm_generate_body",
                new_callable=AsyncMock,
                return_value=(expected_text, ""),
            ) as llm_mock:
                body, astro_context = await generate_prediction_body(
                    session,
                    user,
                    profile,
                    target,
                )

    assert body == expected_text
    assert astro_context["question_archetype_id"] == archetype.id
    assert astro_context["date"] == target.isoformat()
    llm_mock.assert_awaited_once()
    assert llm_mock.await_args.kwargs["archetype"] is archetype


def test_build_prediction_astro_context_includes_archetype_id() -> None:
    ctx = SimpleNamespace(
        model_dump_json_safe=lambda: {"date": "2026-06-14", "natal": {"sun": "Лев"}},
    )
    archetype = pick_question_archetype(uuid4(), date(2026, 6, 14))
    payload = build_prediction_astro_context(ctx, archetype)
    assert payload["question_archetype_id"] == archetype.id
    assert payload["natal"]["sun"] == "Лев"
