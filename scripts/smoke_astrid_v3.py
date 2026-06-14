#!/usr/bin/env python3
"""Smoke: Astrid v3 через Ollama (gemma4:e2b). Запуск: uv run python scripts/smoke_astrid_v3.py"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime
from types import SimpleNamespace
from uuid import UUID
from zoneinfo import ZoneInfo

from astra.astro.schemas import AstroContext, NatalChartData, TransitAspect
from astra.llm.ollama import generate_prediction_body
from astra.llm.prompts.astrid import (
    pick_question_archetype,
    validate_prediction_output,
)

AID_USER = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
MARINA_USER = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


def _profile(user_id: UUID, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=user_id,
        display_name=name,
        birth_date=date(1992, 2, 11),
        birth_time=datetime(1992, 2, 11, 14, 30, tzinfo=ZoneInfo("Europe/Moscow")),
        birth_place="Москва",
        city="Москва",
        timezone="Europe/Moscow",
    )


def _ctx(target: date) -> AstroContext:
    return AstroContext(
        date=target,
        accuracy_tier=100,
        natal={"sun": "Водолей", "moon": "Рак", "asc": "Весы"},
        transits=[
            TransitAspect(
                transit_planet="Марс",
                aspect="трин",
                natal_planet="Венера",
                orb_deg=1.2,
                theme="дела и личные приоритеты",
            ),
            TransitAspect(
                transit_planet="Меркурий",
                aspect="квадрат",
                natal_planet="Луна",
                orb_deg=2.1,
                theme="общение и близкие отношения",
            ),
            TransitAspect(
                transit_planet="Юпитер",
                aspect="секстиль",
                natal_planet="Солнце",
                orb_deg=3.0,
                theme="фокус и намерения дня",
            ),
        ],
    )


def _chart() -> NatalChartData:
    return NatalChartData(
        accuracy_tier=100,
        sun_sign="Водолей",
        moon_sign="Рак",
        asc_sign="Весы",
        timezone="Europe/Moscow",
    )


async def _run_case(name: str, user_id: UUID, target: date) -> bool:
    profile = _profile(user_id, name)
    archetype = pick_question_archetype(user_id, target)
    print("=" * 60)
    print(f"Smoke: {name} · {target.isoformat()} · archetype={archetype.id}")
    print("=" * 60)

    text, reason = await generate_prediction_body(
        _ctx(target),
        profile,
        _chart(),
        archetype=archetype,
    )
    if not text:
        print(f"FAIL: {reason}")
        return False

    err = validate_prediction_output(text, name)
    if err:
        print(f"FAIL validate: {err}")
        print(text)
        return False

    question = text.split("\n\n", 1)[0]
    print(f"Push ({len(question)} симв.): «{question}»")
    print()
    print(text)
    print()
    return True


async def main() -> int:
    target = date.today()
    cases = [
        ("Aidamir", AID_USER, target),
        ("Марина", MARINA_USER, target),
    ]
    results = [await _run_case(*case) for case in cases]
    ok = all(results)
    print("=" * 60)
    print(f"Smoke {'OK' if ok else 'FAILED'}: {sum(results)}/{len(results)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
