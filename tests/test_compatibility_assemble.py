"""Тесты assemble и clamp для совместимости."""

from __future__ import annotations

import json

import pytest

from astra.llm.compatibility_assemble import (
    assemble_llm_output,
    format_orb,
    merge_polish,
    sorted_aspects,
    strength_from_orb,
)
from astra.llm.prompts.compatibility_fixtures import build_aidamir_angela_prompt_input
from astra.llm.schemas.compatibility import MAX_ASPECT_BLOCKS
from astra.llm.schemas.compatibility_raw import CompatibilityPolishRaw
from astra.llm.prompts.compatibility import parse_narrative_skeleton
from astra.llm.text_clamp import clamp_text
from compatibility_llm_samples import sample_content_raw


def test_parse_skeleton_unwraps_schema_style_properties() -> None:
    raw = json.dumps(
        {
            "description": "Шаг 1",
            "properties": {
                "pair_story": "Абзац 1.\n\nАбзац 2.\n\nАбзац 3.",
                "central_tension": "Разный быт",
                "growth_path": "Договор о ритме",
                "metrics": [0.9, 0.7, 0.8, 0.75],
            },
        },
        ensure_ascii=False,
    )
    parsed, error = parse_narrative_skeleton(raw)
    assert error is None
    assert parsed is not None
    assert parsed.central_tension == "Разный быт"
    assert len(parsed.metrics) == 4


def test_clamp_text_by_sentence() -> None:
    text = "Первое предложение. Второе очень длинное предложение с деталями."
    result = clamp_text(text, 35)
    assert result.endswith("…")
    assert len(result) <= 35


def test_strength_from_orb_buckets() -> None:
    assert strength_from_orb(0.13) == "Очень сильно"
    assert strength_from_orb(1.46) == "Сильно"
    assert strength_from_orb(2.28) == "Заметно"
    assert strength_from_orb(5.69) == "Фоновое"


def test_format_orb() -> None:
    assert format_orb(0.13) == "0.13"
    assert format_orb(1.46) == "1.46"
    assert format_orb(2.0) == "2"


def test_assemble_aidamir_angela_buckets() -> None:
    prompt_input = build_aidamir_angela_prompt_input()
    output = assemble_llm_output(sample_content_raw(), prompt_input)

    assert len(output.strong_aspects) == 4
    assert len(output.working_aspects) == 8
    assert float(output.strong_aspects[-1].orb) == pytest.approx(1.16)
    assert all(float(item.orb) < 2.0 for item in output.strong_aspects)
    assert all(2.0 <= float(item.orb) <= 6.0 for item in output.working_aspects)


def test_assemble_orb_146_always_strong() -> None:
    """Prod-кейс: аспект 1.46° всегда в strong, независимо от «бакета» в голове LLM."""
    prompt_input = build_aidamir_angela_prompt_input()
    aspects = sorted_aspects(prompt_input)
    modified = [
        aspect.model_copy(update={"orb_deg": 1.46}) if aspect.orb_deg == 1.16 else aspect
        for aspect in aspects
    ]
    prompt_input = prompt_input.model_copy(update={"aspects": modified})

    output = assemble_llm_output(sample_content_raw(), prompt_input)
    strong_orbs = [float(a.orb) for a in output.strong_aspects]
    working_orbs = [float(a.orb) for a in output.working_aspects]
    assert 1.46 in strong_orbs
    assert 1.46 not in working_orbs


def test_assemble_clamps_long_natal_insight() -> None:
    prompt_input = build_aidamir_angela_prompt_input()
    long_insight = "А" * 400
    content = sample_content_raw(natal_insight=long_insight)
    output = assemble_llm_output(content, prompt_input)
    assert len(output.natal_insight) <= 260


def test_merge_polish_keeps_metrics_and_zones() -> None:
    prompt_input = build_aidamir_angela_prompt_input()
    content = sample_content_raw()
    polish = CompatibilityPolishRaw(
        tldr="Обновлённый tldr с конкретикой и теплом для пары.",
        pair_story=content.pair_story,
        natal_insight=content.natal_insight,
        conclusion_quote=content.conclusion_quote,
        conclusion_tip=content.conclusion_tip,
        aspect_interpretations=content.aspect_interpretations,
    )
    merged = merge_polish(content, polish)
    assert merged.metrics == content.metrics
    assert merged.zone_items == content.zone_items
    assert "Обновлённый" in merged.tldr


def test_assemble_trims_extra_working_aspects() -> None:
    """Плотная пара: лишние широкие орбы отбрасываются, а не роняют сборку.

    Прод-кейс: у пары набралось 16 «рабочих» аспектов, в раздел помещается 12,
    и вся сборка падала уже после оплаты генерации.
    """
    prompt_input = build_aidamir_angela_prompt_input()
    aspects = sorted_aspects(prompt_input)

    extra = []
    orb = 2.5
    while len(aspects) + len(extra) < 20:
        extra.append(aspects[-1].model_copy(update={"orb_deg": round(orb, 2)}))
        orb += 0.1

    prompt_input = prompt_input.model_copy(update={"aspects": [*aspects, *extra]})
    raw = sample_content_raw()
    interpretations = list(raw.aspect_interpretations)
    interpretations += [interpretations[-1].model_copy() for _ in extra]
    raw = raw.model_copy(update={"aspect_interpretations": interpretations})

    output = assemble_llm_output(raw, prompt_input)

    assert len(output.working_aspects) == MAX_ASPECT_BLOCKS
    orbs = [float(item.orb) for item in output.working_aspects]
    assert orbs == sorted(orbs)  # оставили самые точные, отбросили самый фон
    assert all(2.0 <= value <= 6.0 for value in orbs)


def test_trim_keeps_everything_when_it_fits() -> None:
    prompt_input = build_aidamir_angela_prompt_input()
    output = assemble_llm_output(sample_content_raw(), prompt_input)
    assert len(output.working_aspects) == 8  # обрезка не трогает нормальные пары
