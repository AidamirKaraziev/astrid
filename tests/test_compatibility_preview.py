from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from astra.llm.compatibility_generate import (
    build_compatibility_completion_request,
    generate_compatibility_output,
)
from astra.llm.api.deepseek import DeepSeekProvider
from astra.llm.api.openai import OpenAIProvider
from astra.llm.prompts.compatibility_fixtures import build_aidamir_angela_prompt_input
from astra.llm.types import CompletionResult
from astra.telegram.handlers.compatibility_preview import (
    DEEPSEEK_NOT_CONFIGURED_TEXT,
    _failure_message,
    compatibility_deepseek_preview,
)


def test_build_compatibility_completion_request_openai_json_mode() -> None:
    settings = SimpleNamespace(
        openai_timeout_seconds=180.0,
        deepseek_timeout_seconds=120.0,
        grok_timeout_seconds=90.0,
        gemini_timeout_seconds=45.0,
        openrouter_timeout_seconds=75.0,
        ollama_timeout_seconds=120.0,
    )
    provider = OpenAIProvider(settings)
    request = build_compatibility_completion_request(
        build_aidamir_angela_prompt_input(),
        provider,
        settings,
    )
    assert request.extra["json_mode"] is True
    assert request.temperature is None
    assert request.max_tokens == 8192
    assert request.timeout_seconds == 180.0
    assert request.messages[0].role == "system"
    assert "Astra" in request.messages[0].content
    assert "synastry_aspects" in request.messages[1].content


def test_build_compatibility_completion_request_deepseek() -> None:
    settings = SimpleNamespace(
        openai_timeout_seconds=180.0,
        deepseek_timeout_seconds=120.0,
        grok_timeout_seconds=90.0,
        gemini_timeout_seconds=45.0,
        openrouter_timeout_seconds=75.0,
        ollama_timeout_seconds=120.0,
    )
    provider = DeepSeekProvider(settings)
    request = build_compatibility_completion_request(
        build_aidamir_angela_prompt_input(),
        provider,
        settings,
    )
    assert request.extra["json_mode"] is True
    assert request.extra["thinking_disabled"] is True
    assert request.temperature == 0.7
    assert request.max_tokens == 8192
    assert request.timeout_seconds == 120.0


@pytest.mark.anyio
async def test_generate_compatibility_output_success() -> None:
    provider = AsyncMock()
    provider.name = "openai"
    valid_json = (
        '{"tldr":"Химия между вами реальная — Солнце и Марс сходятся почти идеально. '
        'Главная задача: перевести разные эмоциональные языки, особенно в быту.",'
        '"natal_insight":"Воздух + огонь: идейный союз. Луна Дева ↔ Близнецы — разный быт.",'
        '"metrics":['
        '{"label":"Притяжение","value":0.9},'
        '{"label":"Эмоциональный контакт","value":0.7},'
        '{"label":"Общение","value":0.8},'
        '{"label":"Долгосрочность","value":0.75}],'
        '"strong_aspects":[{"aspect_type":"соединение","from_planet":"Солнце · Водолей",'
        '"to_planet":"Марс · Водолей","orb":"0.13","strength":"Очень сильно",'
        '"headline":"Он включает её инициативу","body":"Самый мощный аспект пары."}],'
        '"working_aspects":[{"aspect_type":"квадрат","from_planet":"Сатурн · Овен",'
        '"to_planet":"Юпитер · Рак","orb":"2.28","strength":"Заметно",'
        '"headline":"Разный темп роста","body":"Договаривайтесь о шагах, не о принципах."}],'
        '"zone_blocks":['
        '{"title":"Что работает само","items":["a","b","c"]},'
        '{"title":"Зоны роста","items":["d","e","f"]},'
        '{"title":"Опора пары","items":["g","h","i"]}],'
        '"conclusion_quote":"Химия здесь реальная — её не нужно создавать. '
        'Задача пары: научиться переводить внутренние языки друг другу.",'
        '"conclusion_tip":"Один вечер без телефонов — расскажите, что для вас значит забота.",'
        '"working_aspects_intro":"Орб 2–6° — требуют внимания"}'
    )
    provider.complete = AsyncMock(return_value=CompletionResult(valid_json))

    output, reason = await generate_compatibility_output(
        build_aidamir_angela_prompt_input(),
        provider,
    )

    assert output is not None
    assert "Химия" in output.tldr
    assert reason == ""


def test_failure_message_maps_known_reasons() -> None:
    assert _failure_message("timeout").startswith("DeepSeek не ответил")
    assert _failure_message("http_401").startswith("DeepSeek API")
    assert _failure_message("http_429:rate limit").startswith("DeepSeek вернул 429")
    assert _failure_message("disabled") == DEEPSEEK_NOT_CONFIGURED_TEXT
    assert _failure_message("validation: bad").startswith("Модель вернула невалидный JSON")


@pytest.mark.anyio
async def test_compatibility_deepseek_preview_not_configured() -> None:
    message = AsyncMock()
    message.from_user.id = 42
    message.answer = AsyncMock()
    session = AsyncMock()

    user = SimpleNamespace(
        id=1,
        onboarding_completed=True,
        profile=SimpleNamespace(timezone="Europe/Moscow"),
    )

    with patch(
        "astra.telegram.handlers.compatibility_preview.users_crud.get_user_by_telegram_id",
        new_callable=AsyncMock,
        return_value=user,
    ):
        with patch(
            "astra.telegram.handlers.compatibility_preview.get_deepseek_provider",
        ) as get_provider:
            get_provider.return_value.is_configured.return_value = False
            await compatibility_deepseek_preview(message, session)

    message.answer.assert_awaited_once()
    assert "DEEPSEEK_ENABLED" in message.answer.await_args.args[0]
