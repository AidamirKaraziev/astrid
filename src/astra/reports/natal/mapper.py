"""Преобразование NatalLlmOutput + FullNatalChart → NatalReportData для PDF."""

from __future__ import annotations

from astra.astro.schemas import FullNatalChart
from astra.llm.schemas.natal import NatalLlmOutput
from astra.reports.natal.types import NatalReportData, PlanetCard, SphereBlock
from astra.reports.theme import (
    ACCENT_BLUE,
    ACCENT_PURPLE,
    GOLD,
    SQUARE_COLOR,
    TRINE_COLOR,
)
from astra.reports.types import AspectData, MetricScore, ZoneBlock

_METRIC_COLORS = {
    "Энергия": SQUARE_COLOR,
    "Эмоции": ACCENT_PURPLE,
    "Коммуникация": ACCENT_BLUE,
    "Устойчивость": TRINE_COLOR,
}

_ZONE_COLORS = {
    "Сильные стороны": TRINE_COLOR,
    "Зоны роста": SQUARE_COLOR,
    "Опоры": GOLD,
}


def _planet_cards(items) -> tuple[PlanetCard, ...]:  # noqa: ANN001
    return tuple(
        PlanetCard(
            point_key=item.point_key,
            title=item.title,
            caption=item.caption,
            text=item.text,
        )
        for item in items
    )


def _aspect_cards(items) -> tuple[AspectData, ...]:  # noqa: ANN001
    return tuple(
        AspectData(
            aspect_type=item.aspect_type,
            from_planet=item.from_planet,
            to_planet=item.to_planet,
            orb=item.orb,
            strength=item.strength,
            headline=item.headline,
            body=item.body,
        )
        for item in items
    )


def llm_output_to_report_data(
    llm: NatalLlmOutput,
    chart: FullNatalChart,
    *,
    person_name: str,
    person_subtitle: str,
) -> NatalReportData:
    return NatalReportData(
        person_name=person_name,
        person_subtitle=person_subtitle,
        chart=chart,
        tldr=llm.tldr,
        core_story=llm.core_story,
        metrics=tuple(
            MetricScore(m.label, m.value, _METRIC_COLORS[m.label]) for m in llm.metrics
        ),
        personality=_planet_cards(llm.personality),
        mind_feelings_action=_planet_cards(llm.mind_feelings_action),
        strong_aspects=_aspect_cards(llm.strong_aspects),
        working_aspects=_aspect_cards(llm.working_aspects),
        spheres=tuple(
            SphereBlock(title=s.title, factors=s.factors, text=s.text, tip=s.tip)
            for s in llm.spheres
        ),
        karmic=_planet_cards(llm.karmic),
        zone_blocks=tuple(
            ZoneBlock(title=z.title, color=_ZONE_COLORS[z.title], items=tuple(z.items))
            for z in llm.zone_blocks
        ),
        practical_tips=tuple(llm.practical_tips),
        conclusion_quote=llm.conclusion_quote,
        conclusion_tip=llm.conclusion_tip,
        balance_note=llm.balance_note,
        accuracy_note=llm.accuracy_note,
    )
