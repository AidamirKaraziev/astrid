"""Тесты astro/synastry и compatibility service helpers."""

from __future__ import annotations

from types import SimpleNamespace

from astra.astro.schemas import NatalChartData
from astra.astro.synastry import chart_to_natal_dict
from astra.compatibility.enums import RelationshipContext
from astra.services.compatibility_service import (
    _TELEGRAM_DOCUMENT_CAPTION_MAX,
    build_report_title,
    format_compatibility_pdf_caption,
)


def test_chart_to_natal_dict_includes_planet_signs() -> None:
    chart = NatalChartData(
        accuracy_tier=100,
        sun_sign="Водолей",
        moon_sign="Дева",
        asc_sign="Стрелец",
        planet_signs={
            "mercury": "Водолей",
            "venus": "Козерог",
            "mars": "Рыбы",
        },
    )
    natal = chart_to_natal_dict(chart)
    assert natal["sun"] == "Водолей"
    assert natal["mercury"] == "Водолей"
    assert natal["mars"] == "Рыбы"


def test_build_report_title() -> None:
    title = build_report_title("Айдамир", "Анжела", RelationshipContext.LOVE)
    assert "Айдамир" in title
    assert "Анжела" in title
    assert "Отношения" in title


def _report_stub(
    *,
    title: str = "Aidamir × анжела · 💑 Отношения",
    llm_output: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(title=title, llm_output=llm_output)


def test_format_compatibility_pdf_caption_with_tldr() -> None:
    tldr = (
        "Искра между вами — с первого взгляда, но бытовые ритмы требуют настройки. "
        "Притяжение мощное, дальше — работа над компромиссами."
    )
    report = _report_stub(llm_output={"tldr": tldr})
    caption = format_compatibility_pdf_caption(report)
    assert caption.startswith(tldr)
    assert caption.endswith("💕 Aidamir × анжела · 💑 Отношения")
    assert "\n\n" in caption


def test_format_compatibility_pdf_caption_without_llm_output() -> None:
    report = _report_stub()
    assert format_compatibility_pdf_caption(report) == "💕 Aidamir × анжела · 💑 Отношения"


def test_format_compatibility_pdf_caption_truncates_long_tldr() -> None:
    title = "A × B · 💑 Отношения"
    footer = f"💕 {title}"
    tldr = "а" * (_TELEGRAM_DOCUMENT_CAPTION_MAX - len(footer))
    report = _report_stub(title=title, llm_output={"tldr": tldr})
    caption = format_compatibility_pdf_caption(report)
    assert len(caption) <= _TELEGRAM_DOCUMENT_CAPTION_MAX
    assert caption.endswith(footer)
    assert "…" in caption
