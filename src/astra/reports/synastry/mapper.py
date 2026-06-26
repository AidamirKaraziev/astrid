"""Маппинг LLM JSON + входных данных → SynastryReportData для PDF."""

from __future__ import annotations

from astra.llm.schemas.compatibility import (
    NATAL_PLANET_KEYS,
    CompatibilityLlmOutput,
    CompatibilityPersonInput,
    CompatibilityPromptInput,
    LlmAspectBlock,
)
from astra.reports.synastry.theme import (
    ACCENT_BLUE,
    ACCENT_PURPLE,
    CONJ_COLOR,
    GOLD,
    SQUARE_COLOR,
    TRINE_COLOR,
)
from astra.reports.synastry.types import (
    AspectData,
    MetricScore,
    PersonData,
    SynastryReportData,
    ZoneBlock,
)

_METRIC_COLORS = {
    "Притяжение": CONJ_COLOR,
    "Эмоциональный контакт": ACCENT_BLUE,
    "Общение": TRINE_COLOR,
    "Долгосрочность": GOLD,
}

_ZONE_COLORS = {
    "Что работает само": TRINE_COLOR,
    "Зоны роста": SQUARE_COLOR,
    "Опора пары": GOLD,
}


def _format_subtitle(person: CompatibilityPersonInput) -> str:
    d = person.birth_date
    return f"{d.day:02d}.{d.month:02d}.{d.year} · {person.birth_place}"


def _person_data(person: CompatibilityPersonInput, *, accent) -> PersonData:  # noqa: ANN001
    planets = tuple(
        (key, person.natal[key])
        for key in NATAL_PLANET_KEYS
        if key in person.natal
    )
    return PersonData(
        name=person.name,
        subtitle=_format_subtitle(person),
        accent=accent,
        planets=planets,
    )


def _aspect_data(block: LlmAspectBlock) -> AspectData:
    return AspectData(
        aspect_type=block.aspect_type,
        from_planet=block.from_planet,
        to_planet=block.to_planet,
        orb=block.orb,
        strength=block.strength,
        headline=block.headline,
        body=block.body,
    )


def llm_output_to_report_data(
    prompt_input: CompatibilityPromptInput,
    llm: CompatibilityLlmOutput,
) -> SynastryReportData:
    """Собрать PDF-модель: наталы и цвета из кода, тексты из LLM."""
    return SynastryReportData(
        person_a=_person_data(prompt_input.person_a, accent=ACCENT_BLUE),
        person_b=_person_data(prompt_input.person_b, accent=ACCENT_PURPLE),
        tldr=llm.tldr,
        natal_insight=llm.natal_insight,
        metrics=tuple(
            MetricScore(m.label, m.value, _METRIC_COLORS[m.label])
            for m in llm.metrics
        ),
        strong_aspects=tuple(_aspect_data(a) for a in llm.strong_aspects),
        working_aspects=tuple(_aspect_data(a) for a in llm.working_aspects),
        zone_blocks=tuple(
            ZoneBlock(z.title, _ZONE_COLORS[z.title], tuple(z.items))
            for z in llm.zone_blocks
        ),
        conclusion_quote=llm.conclusion_quote,
        conclusion_tip=llm.conclusion_tip,
        working_aspects_intro=llm.working_aspects_intro,
    )
