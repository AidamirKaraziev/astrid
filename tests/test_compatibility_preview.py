from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.llm.compatibility_generate import (
    build_compatibility_completion_request,
    generate_compatibility_output,
)
from astra.llm.api.deepseek import DeepSeekProvider
from astra.llm.api.openai import OpenAIProvider
from astra.llm.prompts.compatibility_fixtures import build_aidamir_angela_prompt_input
from astra.llm.types import CompletionResult
from astra.reports.synastry.stub_report import build_aidamir_angela_stub_report
from astra.telegram.handlers.compatibility_preview import (
    COMPATIBILITY_PDF_FAILED,
    compatibility_pdf_stub,
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


def test_build_aidamir_angela_stub_report() -> None:
    report = build_aidamir_angela_stub_report()
    assert report.person_a.name == "Айдамир"
    assert report.person_b.name == "Анжела"
    assert "Притяжение" in report.tldr
    assert len(report.strong_aspects) == 3
    assert len(report.working_aspects) == 9
    assert report.metrics[0].value == pytest.approx(0.95)


@pytest.mark.anyio
async def test_compatibility_pdf_stub_sends_document() -> None:
    message = AsyncMock()
    message.from_user.id = 42
    message.answer = AsyncMock()
    message.answer_document = AsyncMock()
    session = AsyncMock()

    user = SimpleNamespace(
        id=1,
        onboarding_completed=True,
        profile=SimpleNamespace(gender="мужчина", timezone="Europe/Moscow"),
    )
    pdf_path = MagicMock()
    pdf_path.unlink = MagicMock()

    with patch(
        "astra.telegram.handlers.compatibility_preview.users_crud.get_user_by_telegram_id",
        new_callable=AsyncMock,
        return_value=user,
    ):
        with patch(
            "astra.telegram.handlers.compatibility_preview.render_stub_compatibility_pdf",
            return_value=pdf_path,
        ):
            with patch(
                "astra.telegram.handlers.compatibility_preview.FSInputFile",
                return_value="doc",
            ) as fs_input:
                await compatibility_pdf_stub(message, session)

    message.answer.assert_awaited_once()
    fs_input.assert_called_once_with(pdf_path, filename="synastry-aidamir-angela.pdf")
    message.answer_document.assert_awaited_once()
    pdf_path.unlink.assert_called_once_with(missing_ok=True)


@pytest.mark.anyio
async def test_compatibility_pdf_stub_failure() -> None:
    message = AsyncMock()
    message.from_user.id = 42
    message.answer = AsyncMock()
    message.answer_document = AsyncMock()
    session = AsyncMock()

    user = SimpleNamespace(
        id=1,
        onboarding_completed=True,
        profile=SimpleNamespace(gender="мужчина", timezone="Europe/Moscow"),
    )

    with patch(
        "astra.telegram.handlers.compatibility_preview.users_crud.get_user_by_telegram_id",
        new_callable=AsyncMock,
        return_value=user,
    ):
        with patch(
            "astra.telegram.handlers.compatibility_preview.render_stub_compatibility_pdf",
            side_effect=RuntimeError("pdf boom"),
        ):
            await compatibility_pdf_stub(message, session)

    assert message.answer.await_count == 2
    assert COMPATIBILITY_PDF_FAILED in message.answer.await_args_list[-1].args[0]


@pytest.mark.anyio
async def test_compatibility_pdf_stub_prompts_gender_when_missing() -> None:
    message = AsyncMock()
    message.from_user.id = 42
    message.answer = AsyncMock()
    message.answer_document = AsyncMock()
    session = AsyncMock()

    user = SimpleNamespace(
        id=1,
        onboarding_completed=True,
        profile=SimpleNamespace(gender=None, timezone="Europe/Moscow"),
    )

    with patch(
        "astra.telegram.handlers.compatibility_preview.users_crud.get_user_by_telegram_id",
        new_callable=AsyncMock,
        return_value=user,
    ):
        await compatibility_pdf_stub(message, session)

    message.answer.assert_awaited_once()
    assert "пол" in message.answer.await_args.args[0].lower()
    message.answer_document.assert_not_awaited()
