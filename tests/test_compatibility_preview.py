from types import SimpleNamespace
from unittest.mock import AsyncMock

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
from compatibility_llm_samples import sample_content_raw as _sample_content


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        openai_timeout_seconds=180.0,
        deepseek_timeout_seconds=120.0,
        grok_timeout_seconds=90.0,
        gemini_timeout_seconds=45.0,
        openrouter_timeout_seconds=75.0,
        ollama_timeout_seconds=120.0,
    )


def test_build_compatibility_completion_request_openai_json_mode() -> None:
    provider = OpenAIProvider(_settings())
    request = build_compatibility_completion_request(
        build_aidamir_angela_prompt_input(),
        provider,
        _settings(),
    )
    assert request.extra["json_mode"] is True
    assert request.temperature is None
    assert request.max_tokens == 8192
    assert request.timeout_seconds == 180.0
    assert request.messages[0].role == "system"
    assert "Astra" in request.messages[0].content
    assert "aspect_interpretations" in request.messages[1].content
    assert "properties" not in request.messages[1].content or "не JSON Schema" in request.messages[1].content


def test_build_compatibility_completion_request_deepseek() -> None:
    provider = DeepSeekProvider(_settings())
    request = build_compatibility_completion_request(
        build_aidamir_angela_prompt_input(),
        provider,
        _settings(),
    )
    assert request.extra["json_mode"] is True
    assert request.extra["thinking_disabled"] is True
    assert request.temperature == 0.8
    assert request.max_tokens == 8192
    assert request.timeout_seconds == 120.0


def _pipeline_json_responses(prompt_input) -> list[str]:  # noqa: ANN001
    from astra.llm.schemas.compatibility_raw import (
        CompatibilityNarrativeSkeleton,
        CompatibilityPolishRaw,
    )

    content = _sample_content()
    skeleton = CompatibilityNarrativeSkeleton(
        pair_story=content.pair_story,
        central_tension="Разный бытовой ритм",
        growth_path="Договариваться о правилах",
        metrics=content.metrics,
    )
    polish = CompatibilityPolishRaw(
        tldr="Обновлённый tldr: химия реальная, быт — зона роста.",
        pair_story=content.pair_story,
        natal_insight=content.natal_insight,
        conclusion_quote=content.conclusion_quote,
        conclusion_tip=content.conclusion_tip,
        aspect_interpretations=content.aspect_interpretations,
    )
    return [
        skeleton.model_dump_json(),
        content.model_dump_json(),
        polish.model_dump_json(),
    ]


@pytest.mark.anyio
async def test_generate_compatibility_output_success() -> None:
    prompt_input = build_aidamir_angela_prompt_input()
    provider = AsyncMock()
    provider.name = "openai"
    responses = _pipeline_json_responses(prompt_input)
    provider.complete = AsyncMock(
        side_effect=[CompletionResult(text) for text in responses],
    )

    output, reason = await generate_compatibility_output(prompt_input, provider)

    assert output is not None
    assert "химия" in output.tldr.lower()
    assert output.pair_story
    assert len(output.strong_aspects) == 4
    assert reason == ""
    assert provider.complete.await_count == 3


def test_build_aidamir_angela_stub_report() -> None:
    report = build_aidamir_angela_stub_report()
    assert report.person_a.name == "Айдамир"
    assert report.person_b.name == "Анжела"
    assert report.pair_story
    assert len(report.strong_aspects) == 3
    assert len(report.working_aspects) == 9
    assert report.metrics[0].value == pytest.approx(0.95)
