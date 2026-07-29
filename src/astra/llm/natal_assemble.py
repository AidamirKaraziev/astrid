"""Сборка NatalPromptInput из карты и NatalLlmOutput из сырого LLM."""

from __future__ import annotations

from astra.astro.chart_features import ChartFeatures
from astra.astro.schemas import FullNatalChart
from astra.llm.compatibility_assemble import format_orb, strength_from_orb
from astra.llm.schemas.compatibility import MAX_ASPECT_BLOCKS, LlmAspectBlock
from astra.llm.schemas.natal import (
    NATAL_ASPECTS_LIMIT,
    NATAL_METRIC_LABELS,
    NATAL_SPHERE_TITLES,
    NATAL_ZONE_TITLES,
    NatalAspectPromptInput,
    NatalLlmOutput,
    NatalMetric,
    NatalPersonInput,
    NatalPlanetText,
    NatalPointInput,
    NatalPromptInput,
    NatalSphereBlock,
    NatalZoneBlock,
)
from astra.llm.schemas.natal_raw import NatalContentRaw, NatalPolishRaw
from astra.llm.text_clamp import clamp_text

_LIMITS = {
    "tldr": 340,
    "core_story": 1400,
    "planet_text": 450,
    "headline": 56,
    "body": 300,
    "sphere_text": 520,
    "sphere_tip": 180,
    "zone_item": 110,
    "tip": 200,
    "balance_note": 280,
    "conclusion_quote": 420,
    "conclusion_tip": 220,
}

NO_TIME_ACCURACY_NOTE = (
    "Время рождения не указано, поэтому асцендент и дома не рассчитаны — "
    "разбор опирается на положение планет в знаках и аспекты."
)

_MOON_UNCERTAIN_NOTE = (
    " Луна в день рождения меняла знак: её описание может быть неточным."
)


def build_feature_lines(features: ChartFeatures, chart: FullNatalChart) -> list[str]:
    """Человекочитаемые акценты карты для промпта."""
    lines: list[str] = []
    if features.dominant_element:
        lines.append(f"Доминирующая стихия: {features.dominant_element}")
    if features.dominant_modality:
        lines.append(f"Доминирующий крест: {features.dominant_modality}")
    for stellium in features.stellia:
        where = stellium.where if stellium.kind == "house" else f"знаке {stellium.where}"
        lines.append(f"Стеллиум в {where}: {', '.join(stellium.planets)}")
    if features.aspect_king:
        lines.append(f"Король аспектов (самая связанная планета): {features.aspect_king}")
    if features.angular_planets:
        lines.append(f"Планеты на углах карты (усилены): {', '.join(features.angular_planets)}")
    for config in features.configurations:
        if config.apex:
            lines.append(
                f"Конфигурация {config.kind_ru} с вершиной {config.apex}: "
                f"{', '.join(config.planets)}"
            )
        else:
            lines.append(f"Конфигурация {config.kind_ru}: {', '.join(config.planets)}")
    if features.retrograde_planets:
        lines.append(f"Ретроградные: {', '.join(features.retrograde_planets)}")
    if features.dignified_planets:
        pairs = [f"{name} ({dignity})" for name, dignity in features.dignified_planets.items()]
        lines.append(f"Эссенциальные достоинства: {', '.join(pairs)}")
    if features.hemisphere_emphasis:
        lines.append(f"Акцент полусфер: {features.hemisphere_emphasis}")
    if chart.moon_phase:
        lines.append(f"Фаза Луны при рождении: {chart.moon_phase}")
    return lines


def build_natal_prompt_input(
    chart: FullNatalChart,
    features: ChartFeatures,
    *,
    name: str,
    gender: str | None,
    birth_date,  # noqa: ANN001 — date
    birth_time_label: str | None,
    birth_place: str,
) -> NatalPromptInput:
    points = [
        NatalPointInput(
            key=p.name,
            name=p.name_ru,
            sign=p.sign,
            sign_deg=round(p.sign_deg, 1),
            house=p.house,
            retrograde=p.retrograde,
            dignity=p.dignity,
        )
        for p in chart.points
    ]

    point_ru = {p.name: p.name_ru for p in chart.points}
    point_ru["Ascendant"] = "Асцендент"
    point_ru["Medium_Coeli"] = "MC"

    aspects = [
        NatalAspectPromptInput(
            p1_key=a.p1,
            p1=point_ru.get(a.p1, a.p1_ru),
            p2_key=a.p2,
            p2=point_ru.get(a.p2, a.p2_ru),
            aspect=a.aspect,  # type: ignore[arg-type]
            orb_deg=a.orb_deg,
        )
        for a in chart.aspects[:NATAL_ASPECTS_LIMIT]
    ]

    return NatalPromptInput(
        person=NatalPersonInput(
            name=name,
            gender=gender,
            birth_date=birth_date,
            birth_time=birth_time_label,
            birth_place=birth_place,
            timezone=chart.timezone,
            has_time=chart.has_time,
        ),
        points=points,
        asc_sign=chart.asc.sign if chart.asc else None,
        mc_sign=chart.mc.sign if chart.mc else None,
        aspects=aspects,
        feature_lines=build_feature_lines(features, chart),
        element_balance=chart.element_balance,
        modality_balance=chart.modality_balance,
        moon_phase=chart.moon_phase,
        moon_sign_uncertain=chart.moon_sign_uncertain,
    )


def merge_polish(content: NatalContentRaw, polish: NatalPolishRaw) -> NatalContentRaw:
    return content.model_copy(
        update={
            "tldr": polish.tldr,
            "core_story": polish.core_story,
            "sun_text": polish.sun_text,
            "moon_text": polish.moon_text,
            "asc_text": polish.asc_text if polish.asc_text else content.asc_text,
            "mercury_text": polish.mercury_text,
            "venus_text": polish.venus_text,
            "mars_text": polish.mars_text,
            "aspect_interpretations": polish.aspect_interpretations,
            "spheres": polish.spheres,
            "north_node_text": polish.north_node_text,
            "south_node_text": polish.south_node_text,
            "lilith_text": polish.lilith_text,
            "balance_note": polish.balance_note,
            "conclusion_quote": polish.conclusion_quote,
            "conclusion_tip": polish.conclusion_tip,
        }
    )


def _sign_prepositional(sign: str) -> str:
    from astra.astro.constants import SIGN_RU_PREPOSITIONAL

    return SIGN_RU_PREPOSITIONAL.get(sign, sign)


def _point_title(point: NatalPointInput) -> str:
    title = f"{point.name} в {_sign_prepositional(point.sign)}"
    if point.house is not None:
        title += f" · {point.house} дом"
    return title


def _point_caption(point: NatalPointInput) -> str:
    parts: list[str] = []
    if point.retrograde:
        parts.append("ретроградный")
    if point.dignity:
        parts.append(point.dignity)
    return " · ".join(parts)


def _planet_text(
    prompt_input: NatalPromptInput,
    key: str,
    text: str,
    *,
    title_override: str | None = None,
) -> NatalPlanetText:
    point = prompt_input.point(key)
    title = title_override or (_point_title(point) if point else key)
    caption = _point_caption(point) if point else ""
    return NatalPlanetText(
        point_key=key,
        title=clamp_text(title, 64),
        caption=clamp_text(caption, 48),
        text=clamp_text(text, _LIMITS["planet_text"]),
    )


def _planet_label(prompt_input: NatalPromptInput, key: str, name_ru: str) -> str:
    point = prompt_input.point(key)
    if point is not None:
        return f"{point.name} · {point.sign}"
    if key == "Ascendant" and prompt_input.asc_sign:
        return f"Асцендент · {prompt_input.asc_sign}"
    if key == "Medium_Coeli" and prompt_input.mc_sign:
        return f"MC · {prompt_input.mc_sign}"
    return name_ru


def _sphere_factors(prompt_input: NatalPromptInput, sphere_title: str) -> str:
    """Детерминированная строка факторов для карточки сферы."""
    parts: list[str] = []
    if sphere_title == NATAL_SPHERE_TITLES[0]:  # призвание
        if prompt_input.mc_sign:
            parts.append(f"MC в {prompt_input.mc_sign}")
        for key in ("Saturn", "Jupiter"):
            point = prompt_input.point(key)
            if point and point.house == 10:
                parts.append(f"{point.name} в 10 доме")
        if not parts:
            sun = prompt_input.point("Sun")
            if sun:
                parts.append(_point_title(sun))
    elif sphere_title == NATAL_SPHERE_TITLES[1]:  # отношения
        for key in ("Venus", "Mars", "Moon"):
            point = prompt_input.point(key)
            if point:
                parts.append(f"{point.name} в {point.sign}")
            if len(parts) == 2:
                break
    else:  # ресурсы
        for point in prompt_input.points:
            if point.house in (2, 8):
                parts.append(f"{point.name} в {point.house} доме")
            if len(parts) == 2:
                break
        if not parts:
            venus = prompt_input.point("Venus")
            if venus:
                parts.append(_point_title(venus))
    return clamp_text(" · ".join(parts), 90)


def _trim_aspects(blocks: list[LlmAspectBlock]) -> list[LlmAspectBlock]:
    """Оставить самые точные аспекты: список уже отсортирован по орбу.

    В раздел отчёта помещается MAX_ASPECT_BLOCKS карточек. У карты с плотной
    сеткой связей их набирается больше — лишние (с самым широким орбом) просто
    фон, и раньше они роняли всю сборку уже после оплаты генерации.
    """
    return blocks[:MAX_ASPECT_BLOCKS]


def assemble_llm_output(
    raw: NatalContentRaw,
    prompt_input: NatalPromptInput,
) -> NatalLlmOutput:
    aspects = prompt_input.aspects
    if len(raw.aspect_interpretations) != len(aspects):
        msg = (
            f"aspect_interpretations: ожидалось {len(aspects)}, "
            f"получено {len(raw.aspect_interpretations)}"
        )
        raise ValueError(msg)

    strong: list[LlmAspectBlock] = []
    working: list[LlmAspectBlock] = []
    for aspect, interp in zip(aspects, raw.aspect_interpretations, strict=True):
        headline = interp.headline.strip() or f"{aspect.p1} и {aspect.p2}"
        body = interp.body.strip() or (
            f"Аспект {aspect.aspect} с орбом {format_orb(aspect.orb_deg)}° "
            f"связывает {aspect.p1} и {aspect.p2}."
        )
        block = LlmAspectBlock(
            aspect_type=aspect.aspect,
            from_planet=clamp_text(_planet_label(prompt_input, aspect.p1_key, aspect.p1), 48),
            to_planet=clamp_text(_planet_label(prompt_input, aspect.p2_key, aspect.p2), 48),
            orb=format_orb(aspect.orb_deg),
            strength=strength_from_orb(aspect.orb_deg),
            headline=clamp_text(headline, _LIMITS["headline"]),
            body=clamp_text(body, _LIMITS["body"]),
        )
        if aspect.orb_deg < 2.0:
            strong.append(block)
        else:
            working.append(block)

    personality = [
        _planet_text(prompt_input, "Sun", raw.sun_text),
        _planet_text(prompt_input, "Moon", raw.moon_text),
    ]
    if prompt_input.person.has_time and prompt_input.asc_sign and raw.asc_text:
        personality.append(
            _planet_text(
                prompt_input,
                "Ascendant",
                raw.asc_text,
                title_override=f"Асцендент в {_sign_prepositional(prompt_input.asc_sign)}",
            )
        )

    mind = [
        _planet_text(prompt_input, "Mercury", raw.mercury_text),
        _planet_text(prompt_input, "Venus", raw.venus_text),
        _planet_text(prompt_input, "Mars", raw.mars_text),
    ]

    karmic = [
        _planet_text(prompt_input, "True_North_Lunar_Node", raw.north_node_text),
        _planet_text(prompt_input, "True_South_Lunar_Node", raw.south_node_text),
        _planet_text(prompt_input, "Mean_Lilith", raw.lilith_text),
    ]

    spheres = [
        NatalSphereBlock(
            title=title,  # type: ignore[arg-type]
            factors=_sphere_factors(prompt_input, title),
            text=clamp_text(sphere.text, _LIMITS["sphere_text"]),
            tip=clamp_text(sphere.tip, _LIMITS["sphere_tip"]),
        )
        for title, sphere in zip(NATAL_SPHERE_TITLES, raw.spheres, strict=True)
    ]

    metrics = [
        NatalMetric(label=label, value=float(value))  # type: ignore[arg-type]
        for label, value in zip(NATAL_METRIC_LABELS, raw.metrics, strict=True)
    ]

    zone_blocks = [
        NatalZoneBlock(
            title=title,  # type: ignore[arg-type]
            items=[clamp_text(item, _LIMITS["zone_item"]) for item in items],
        )
        for title, items in zip(NATAL_ZONE_TITLES, raw.zone_items, strict=True)
    ]

    accuracy_note = ""
    if not prompt_input.person.has_time:
        accuracy_note = NO_TIME_ACCURACY_NOTE
        if prompt_input.moon_sign_uncertain:
            accuracy_note += _MOON_UNCERTAIN_NOTE

    return NatalLlmOutput(
        tldr=clamp_text(raw.tldr, _LIMITS["tldr"]),
        core_story=clamp_text(raw.core_story, _LIMITS["core_story"]),
        metrics=metrics,
        personality=personality,
        mind_feelings_action=mind,
        strong_aspects=_trim_aspects(strong),
        working_aspects=_trim_aspects(working),
        spheres=spheres,
        karmic=karmic,
        zone_blocks=zone_blocks,
        practical_tips=[clamp_text(tip, _LIMITS["tip"]) for tip in raw.practical_tips],
        balance_note=clamp_text(raw.balance_note, _LIMITS["balance_note"]),
        accuracy_note=accuracy_note,
        conclusion_quote=clamp_text(raw.conclusion_quote, _LIMITS["conclusion_quote"]),
        conclusion_tip=clamp_text(raw.conclusion_tip, _LIMITS["conclusion_tip"]),
    )
