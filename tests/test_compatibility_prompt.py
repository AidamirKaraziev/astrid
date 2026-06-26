"""Тесты промпта совместимости и схемы под PDF."""

from __future__ import annotations

import json

from astra.llm.prompts.compatibility import (
    COMPATIBILITY_OUTPUT_EXAMPLE,
    build_compatibility_system_prompt,
    build_compatibility_user_message,
    parse_compatibility_response,
)
from astra.llm.prompts.compatibility_fixtures import build_aidamir_angela_prompt_input
from astra.llm.schemas.compatibility import (
    METRIC_LABELS,
    ZONE_BLOCK_TITLES,
    CompatibilityLlmOutput,
)
from astra.reports.synastry.mapper import llm_output_to_report_data
from astra.reports.synastry.sample_data import build_sample_report


def test_system_prompt_pdf_contract() -> None:
    prompt = build_compatibility_system_prompt()
    assert "JSON" in prompt
    assert "PDF" in prompt or "полей" in prompt.lower()


def test_user_message_contains_pdf_field_map() -> None:
    msg = build_compatibility_user_message(build_aidamir_angela_prompt_input())
    assert "tldr" in msg
    assert "strong_aspects" in msg
    assert "zone_blocks" in msg
    assert "conclusion_quote" in msg
    assert "Айдамир" in msg
    assert "orb_deg" in msg
    for label in METRIC_LABELS:
        assert label in msg
    for title in ZONE_BLOCK_TITLES:
        assert title in msg


def test_user_message_aspect_order_by_orb() -> None:
    msg = build_compatibility_user_message(build_aidamir_angela_prompt_input())
    idx_013 = msg.index('"orb_deg": 0.13')
    idx_569 = msg.index('"orb_deg": 5.69')
    assert idx_013 < idx_569


def test_parse_example_json_roundtrip() -> None:
    raw = json.dumps(COMPATIBILITY_OUTPUT_EXAMPLE, ensure_ascii=False)
    parsed, err = parse_compatibility_response(raw)
    assert err is None
    assert parsed is not None
    assert len(parsed.metrics) == 4
    assert parsed.zone_blocks[0].title == "Что работает само"


def test_mapper_produces_valid_report_data() -> None:
    raw = json.dumps(COMPATIBILITY_OUTPUT_EXAMPLE, ensure_ascii=False)
    llm, _ = parse_compatibility_response(raw)
    assert llm is not None
    report = llm_output_to_report_data(build_aidamir_angela_prompt_input(), llm)
    assert report.person_a.name == "Айдамир"
    assert report.person_b.name == "Анжела"
    assert len(report.metrics) == 4
    assert len(report.zone_blocks) == 3
    assert report.strong_aspects[0].aspect_type == "соединение"


def test_sample_report_matches_schema_labels() -> None:
    """Демо-PDF и схема LLM используют одни и те же подписи."""
    sample = build_sample_report()
    assert tuple(m.label for m in sample.metrics) == METRIC_LABELS
    assert tuple(z.title for z in sample.zone_blocks) == ZONE_BLOCK_TITLES


def test_validation_rejects_wrong_metric_order() -> None:
    bad = dict(COMPATIBILITY_OUTPUT_EXAMPLE)
    bad["metrics"] = list(reversed(bad["metrics"]))
    _, err = parse_compatibility_response(json.dumps(bad, ensure_ascii=False))
    assert err is not None
    assert "metrics" in err


def test_validation_rejects_strong_aspect_high_orb() -> None:
    bad = dict(COMPATIBILITY_OUTPUT_EXAMPLE)
    aspects = [dict(bad["strong_aspects"][0])]
    aspects[0]["orb"] = "3.5"
    bad["strong_aspects"] = aspects
    _, err = parse_compatibility_response(json.dumps(bad, ensure_ascii=False))
    assert err is not None
