"""Сборка CompatibilityLlmOutput из сырого LLM + входных аспектов."""

from __future__ import annotations

from astra.llm.schemas.compatibility import (
    MAX_ASPECT_BLOCKS,
    METRIC_LABELS,
    ZONE_BLOCK_TITLES,
    AspectStrength,
    CompatibilityLlmOutput,
    CompatibilityPromptInput,
    LlmAspectBlock,
    LlmMetric,
    LlmZoneBlock,
    SynastryAspectInput,
)
from astra.llm.schemas.compatibility_raw import (
    AspectInterpretationRaw,
    CompatibilityContentRaw,
    CompatibilityPolishRaw,
)
from astra.llm.text_clamp import clamp_text

_PLANET_RU_TO_NATAL_KEY: dict[str, str] = {
    "Солнце": "sun",
    "Луна": "moon",
    "Меркурий": "mercury",
    "Венера": "venus",
    "Марс": "mars",
    "Юпитер": "jupiter",
    "Сатурн": "saturn",
}

_LIMITS = {
    "tldr": 340,
    "pair_story": 1400,
    "natal_insight": 260,
    "headline": 56,
    "body": 300,
    "zone_item": 110,
    "conclusion_quote": 420,
    "conclusion_tip": 220,
}


def sorted_aspects(prompt_input: CompatibilityPromptInput) -> list[SynastryAspectInput]:
    return sorted(prompt_input.aspects, key=lambda aspect: aspect.orb_deg)


def strength_from_orb(orb_deg: float) -> AspectStrength:
    if orb_deg < 0.5:
        return "Очень сильно"
    if orb_deg < 1.5:
        return "Сильно"
    if orb_deg < 4.0:
        return "Заметно"
    return "Фоновое"


def format_orb(orb_deg: float) -> str:
    return f"{orb_deg:.2f}".rstrip("0").rstrip(".")


def merge_polish(
    content: CompatibilityContentRaw,
    polish: CompatibilityPolishRaw,
) -> CompatibilityContentRaw:
    return CompatibilityContentRaw(
        tldr=polish.tldr,
        pair_story=polish.pair_story,
        natal_insight=polish.natal_insight,
        metrics=content.metrics,
        aspect_interpretations=polish.aspect_interpretations,
        zone_items=content.zone_items,
        conclusion_quote=polish.conclusion_quote,
        conclusion_tip=polish.conclusion_tip,
    )


def _person_for_name(
    prompt_input: CompatibilityPromptInput,
    name: str,
):
    if name == prompt_input.person_a.name:
        return prompt_input.person_a
    return prompt_input.person_b


def _planet_label(person, point_ru: str) -> str:  # noqa: ANN001
    key = _PLANET_RU_TO_NATAL_KEY.get(point_ru)
    if key and key in person.natal:
        return f"{point_ru} · {person.natal[key]}"
    return point_ru


def _fallback_interpretation(aspect: SynastryAspectInput) -> AspectInterpretationRaw:
    theme = aspect.theme or "взаимное влияние"
    return AspectInterpretationRaw(
        headline=clamp_text(f"{aspect.from_point} и {aspect.to_point}", _LIMITS["headline"]),
        body=clamp_text(
            f"Аспект {aspect.aspect} с орбом {format_orb(aspect.orb_deg)}°: {theme}.",
            _LIMITS["body"],
        ),
    )


def _clamp_zone_items(zone_items: list[list[str]]) -> list[list[str]]:
    result: list[list[str]] = []
    for block in zone_items:
        result.append([clamp_text(item, _LIMITS["zone_item"]) for item in block])
    return result


def _trim_aspects(blocks: list[LlmAspectBlock]) -> list[LlmAspectBlock]:
    """Оставить самые точные аспекты: аспекты уже отсортированы по орбу.

    В раздел отчёта помещается MAX_ASPECT_BLOCKS карточек. У пары с плотной
    сеткой связей их набирается больше — лишние (с самым широким орбом) просто
    фон, и раньше они роняли всю сборку уже после оплаты генерации.
    """
    return blocks[:MAX_ASPECT_BLOCKS]


def assemble_llm_output(
    raw: CompatibilityContentRaw,
    prompt_input: CompatibilityPromptInput,
) -> CompatibilityLlmOutput:
    aspects = sorted_aspects(prompt_input)
    if len(raw.aspect_interpretations) != len(aspects):
        msg = (
            f"aspect_interpretations: ожидалось {len(aspects)}, "
            f"получено {len(raw.aspect_interpretations)}"
        )
        raise ValueError(msg)

    strong: list[LlmAspectBlock] = []
    working: list[LlmAspectBlock] = []

    for aspect, interpretation in zip(aspects, raw.aspect_interpretations, strict=True):
        interp = interpretation
        if not interp.headline.strip() or not interp.body.strip():
            interp = _fallback_interpretation(aspect)

        from_person = _person_for_name(prompt_input, aspect.from_person)
        to_person = _person_for_name(prompt_input, aspect.to_person)
        block = LlmAspectBlock(
            aspect_type=aspect.aspect,
            from_planet=_planet_label(from_person, aspect.from_point),
            to_planet=_planet_label(to_person, aspect.to_point),
            orb=format_orb(aspect.orb_deg),
            strength=strength_from_orb(aspect.orb_deg),
            headline=clamp_text(interp.headline, _LIMITS["headline"]),
            body=clamp_text(interp.body, _LIMITS["body"]),
        )
        if aspect.orb_deg < 2.0:
            strong.append(block)
        else:
            working.append(block)

    metrics = [
        LlmMetric(label=label, value=float(value))  # type: ignore[arg-type]
        for label, value in zip(METRIC_LABELS, raw.metrics, strict=True)
    ]

    zone_blocks = [
        LlmZoneBlock(title=title, items=items)  # type: ignore[arg-type]
        for title, items in zip(ZONE_BLOCK_TITLES, _clamp_zone_items(raw.zone_items), strict=True)
    ]

    return CompatibilityLlmOutput(
        tldr=clamp_text(raw.tldr, _LIMITS["tldr"]),
        pair_story=clamp_text(raw.pair_story, _LIMITS["pair_story"]),
        natal_insight=clamp_text(raw.natal_insight, _LIMITS["natal_insight"]),
        metrics=metrics,
        strong_aspects=_trim_aspects(strong),
        working_aspects=_trim_aspects(working),
        zone_blocks=zone_blocks,
        conclusion_quote=clamp_text(raw.conclusion_quote, _LIMITS["conclusion_quote"]),
        conclusion_tip=clamp_text(raw.conclusion_tip, _LIMITS["conclusion_tip"]),
    )
