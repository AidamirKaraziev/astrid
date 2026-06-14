#!/usr/bin/env python3
"""E2E Astrid v3: чеклист + 3 даты + latency. Запуск: uv run python scripts/e2e_astrid_v3.py"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID
from zoneinfo import ZoneInfo

from astra.astro.schemas import AstroContext, NatalChartData, TransitAspect
from astra.llm.ollama import generate_prediction_body
from astra.llm.prompts.astrid import pick_question_archetype
from astra.llm.prompts.astrid_checklist import CheckResult, checklist_passed, run_v3_checklist

AID_USER = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


@dataclass
class CaseReport:
    label: str
    target: str
    archetype_id: str
    latency_sec: float
    passed: bool
    failure_reason: str | None
    question: str | None
    checks: list[dict[str, object]]


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


def _print_checks(checks: list[CheckResult]) -> None:
    for item in checks:
        mark = "✓" if item.passed else "✗"
        print(f"  {mark} {item.name}: {item.detail}")


async def _run_case(label: str, target: date) -> CaseReport:
    name = "Aidamir"
    profile = _profile(AID_USER, name)
    archetype = pick_question_archetype(AID_USER, target)
    print("=" * 60)
    print(f"E2E: {label} · {target.isoformat()} · archetype={archetype.id}")
    print("=" * 60)

    started = time.monotonic()
    text, reason = await generate_prediction_body(
        _ctx(target),
        profile,
        _chart(),
        archetype=archetype,
    )
    latency = time.monotonic() - started

    if not text:
        print(f"FAIL generation: {reason} ({latency:.1f}s)")
        return CaseReport(
            label=label,
            target=target.isoformat(),
            archetype_id=archetype.id,
            latency_sec=round(latency, 2),
            passed=False,
            failure_reason=reason,
            question=None,
            checks=[],
        )

    checks = run_v3_checklist(text, name)
    _print_checks(checks)
    question = text.split("\n\n", 1)[0]
    print(f"\nPush ({len(question)} симв.): «{question}»")
    print(f"Latency: {latency:.1f}s\n")
    print(text)
    print()

    passed = checklist_passed(checks)
    return CaseReport(
        label=label,
        target=target.isoformat(),
        archetype_id=archetype.id,
        latency_sec=round(latency, 2),
        passed=passed,
        failure_reason=None if passed else "checklist_failed",
        question=question,
        checks=[asdict(item) for item in checks],
    )


async def main() -> int:
    parser = argparse.ArgumentParser(description="E2E Astrid v3 через Ollama")
    parser.add_argument(
        "--json",
        action="store_true",
        help="вывести JSON-отчёт в конце",
    )
    args = parser.parse_args()

    base = date.today()
    cases = [
        ("сегодня", base),
        ("завтра", base + timedelta(days=1)),
        ("+2 дня", base + timedelta(days=2)),
    ]

    reports = [await _run_case(label, target) for label, target in cases]
    passed = sum(1 for report in reports if report.passed)
    latencies = [report.latency_sec for report in reports if report.latency_sec]
    p50 = sorted(latencies)[len(latencies) // 2] if latencies else 0.0

    print("=" * 60)
    print(f"E2E {'OK' if passed == len(reports) else 'FAILED'}: {passed}/{len(reports)}")
    print(f"Latency p50: {p50:.1f}s · archetypes: {[r.archetype_id for r in reports]}")
    print("=" * 60)
    print()
    print("Ручной чеклист TG (deadtiger):")
    print("  [ ] Онбординг → кнопка «🔮 Предсказание» → v3 в чате")
    print("  [ ] Push на iPhone: вопрос целиком виден")
    print("  [ ] Scheduler 09:00 → утреннее предсказание")
    print("  [ ] Retry: при сбое LLM — «Почти готово», затем текст или финальная ошибка")

    if args.json:
        print(json.dumps([asdict(r) for r in reports], ensure_ascii=False, indent=2))

    return 0 if passed == len(reports) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
