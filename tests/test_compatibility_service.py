"""Тесты astro/synastry и compatibility service helpers."""

from __future__ import annotations

from astra.astro.schemas import NatalChartData
from astra.astro.synastry import chart_to_natal_dict
from astra.compatibility.enums import RelationshipContext
from astra.services.compatibility_service import build_report_title


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
