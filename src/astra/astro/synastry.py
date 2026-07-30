"""Расчёт синастрии natal × natal (Kerykeion)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from uuid import UUID

from astra.astro.birth_time import birth_local_datetime
from astra.astro.calculator import kerykeion_available
from astra.astro.constants import ASPECT_EN_TO_RU, PLANET_EN_TO_RU
from astra.astro.schemas import NatalChartData
from astra.compatibility.models import NatalProfile
from astra.llm.schemas.compatibility import SynastryAspectInput
from astra.users.getters import calculate_profile_accuracy
from astra.users.models import Profile

_MAX_ORB = 6.0
_SYNASTRY_POINTS = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn")

_THEME_BY_PAIR: dict[tuple[str, str], str] = {
    ("Sun", "Mars"): "сильное притяжение, инициатива",
    ("Sun", "Moon"): "эмоциональный контакт, взаимопонимание",
    ("Moon", "Moon"): "разный эмоциональный ритм, быт и настроение",
    ("Venus", "Mars"): "химия, флирт, притяжение",
    ("Mercury", "Mercury"): "общение, идеи, диалог",
    ("Saturn", "Saturn"): "ответственность, долгосрочность",
    ("Jupiter", "Venus"): "щедрость, рост, радость",
    ("Saturn", "Jupiter"): "разный темп роста, ожидания vs свобода",
}


@dataclass(frozen=True, slots=True)
class PersonSpec:
    name: str
    birth_date: date
    birth_time: datetime | None
    timezone: str
    chart: NatalChartData


def _default_themes() -> tuple[str, ...]:
    return (
        "взаимное влияние",
        "точка притяжения",
        "зона напряжения",
        "общий ресурс пары",
    )


def _theme(p1: str, p2: str) -> str:
    if (p1, p2) in _THEME_BY_PAIR:
        return _THEME_BY_PAIR[(p1, p2)]
    if (p2, p1) in _THEME_BY_PAIR:
        return _THEME_BY_PAIR[(p2, p1)]
    idx = (hash(p1) ^ hash(p2)) % len(_default_themes())
    return _default_themes()[idx]




def astrological_subject_from_spec(spec: PersonSpec):
    if not kerykeion_available():
        raise RuntimeError("kerykeion is not installed")
    from kerykeion import AstrologicalSubject

    chart = spec.chart
    local_dt = birth_local_datetime(spec.birth_date, spec.birth_time, spec.timezone)
    return AstrologicalSubject(
        spec.name,
        local_dt.year,
        local_dt.month,
        local_dt.day,
        local_dt.hour,
        local_dt.minute,
        lng=chart.birth_lon or 37.6,
        lat=chart.birth_lat or 55.75,
        tz_str=spec.timezone,
    )


def build_synastry_aspects(person_a: PersonSpec, person_b: PersonSpec) -> list[SynastryAspectInput]:
    """Аспекты синастрии между двумя наталами, orb ≤ 6°."""
    if not kerykeion_available():
        from astra.llm.prompts.compatibility_fixtures import build_aidamir_angela_prompt_input

        return build_aidamir_angela_prompt_input().aspects

    from kerykeion import SynastryAspects

    subj_a = astrological_subject_from_spec(person_a)
    subj_b = astrological_subject_from_spec(person_b)
    synastry = SynastryAspects(subj_a, subj_b)

    aspects: list[SynastryAspectInput] = []
    for item in synastry.all_aspects:
        p1_name = item.p1_name
        p2_name = item.p2_name
        if p1_name not in _SYNASTRY_POINTS or p2_name not in _SYNASTRY_POINTS:
            continue
        orb = round(float(item.orbit), 2)
        if orb > _MAX_ORB:
            continue

        if item.p1_owner == person_a.name:
            from_person, to_person = person_a.name, person_b.name
            from_point, to_point = p1_name, p2_name
        elif item.p2_owner == person_a.name:
            from_person, to_person = person_a.name, person_b.name
            from_point, to_point = p2_name, p1_name
        elif item.p1_owner == person_b.name:
            from_person, to_person = person_b.name, person_a.name
            from_point, to_point = p1_name, p2_name
        else:
            from_person, to_person = person_a.name, person_b.name
            from_point, to_point = p1_name, p2_name

        aspect_ru = ASPECT_EN_TO_RU.get(item.aspect, item.aspect)
        if aspect_ru not in {
            "соединение",
            "трин",
            "квадрат",
            "секстиль",
            "оппозиция",
        }:
            continue

        aspects.append(
            SynastryAspectInput(
                from_person=from_person,
                from_point=PLANET_EN_TO_RU.get(from_point, from_point),
                aspect=aspect_ru,  # type: ignore[arg-type]
                to_person=to_person,
                to_point=PLANET_EN_TO_RU.get(to_point, to_point),
                orb_deg=orb,
                theme=_theme(from_point, to_point),
            ),
        )

    aspects.sort(key=lambda a: a.orb_deg)
    return aspects


def profile_accuracy_tier(profile: Profile) -> int:
    tier, _ = calculate_profile_accuracy(profile)
    return tier


def natal_profile_accuracy_tier(row: NatalProfile) -> int:
    has_time = row.birth_time is not None
    has_place = bool(row.birth_place_id or row.birth_place)
    if has_time and has_place:
        return 100
    if has_place:
        return 66
    return 33


def chart_to_natal_dict(chart: NatalChartData) -> dict[str, str]:
    """Словарь знаков планет для промпта совместимости."""
    result: dict[str, str] = {"sun": chart.sun_sign}
    if chart.moon_sign:
        result["moon"] = chart.moon_sign
    if chart.asc_sign:
        result["asc"] = chart.asc_sign
    for key in ("mercury", "venus", "mars", "jupiter", "saturn"):
        sign = chart.planet_signs.get(key)
        if sign:
            result[key] = sign
    return result


def snapshot_from_profile(profile: Profile, chart: NatalChartData) -> dict:
    birth_time = profile.birth_time.isoformat() if profile.birth_time else None
    return {
        "name": profile.display_name,
        "gender": profile.gender,
        "birth_date": profile.birth_date.isoformat(),
        "birth_time": birth_time,
        "birth_place": profile.birth_place or profile.city,
        "birth_place_id": str(profile.birth_place_id) if profile.birth_place_id else None,
        "timezone": profile.timezone,
        "accuracy_tier": profile_accuracy_tier(profile),
        "natal": chart_to_natal_dict(chart),
    }


def snapshot_from_natal_profile(row: NatalProfile, chart: NatalChartData) -> dict:
    birth_time = row.birth_time.isoformat() if row.birth_time else None
    return {
        "name": row.label,
        "gender": row.gender,
        "birth_date": row.birth_date.isoformat(),
        "birth_time": birth_time,
        "birth_place": row.birth_place,
        "birth_place_id": str(row.birth_place_id) if row.birth_place_id else None,
        "timezone": row.timezone,
        "accuracy_tier": natal_profile_accuracy_tier(row),
        "natal": chart_to_natal_dict(chart),
    }
