"""3 промпта без готовых склонений — gemma4:e2b сам склоняет имя."""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from datetime import date, datetime
from textwrap import dedent
from zoneinfo import ZoneInfo

import httpx

warnings.filterwarnings("ignore")
import astra.astro.models  # noqa: F401
import astra.places.models  # noqa: F401
import astra.points.models  # noqa: F401
import astra.predictions.models  # noqa: F401
import astra.referrals.models  # noqa: F401

from astra.astro.calculator import build_natal_chart
from astra.astro.transits import build_daily_context
from astra.llm.prompts.astrid import sanitize_prediction_output
from astra.users.models import Profile

GENDER_RU = {"masc": "мужской", "femn": "женский"}

SYSTEM_BASE = dedent("""
    Ты — Astrid, голос бота Astra. Короткий персональный прогноз на день.

    - Только русский, обращение на «ты».
    - Опирайся на transits; не выдумывай аспекты.
    - Мягко, без запугивания и штампов («звёзды советуют», «вас ждут перемены»).
    - Не используй: ритм, гармония, трансформация, вибрации, энергетика.

    Формат:

    ✨ Прогноз дня

    [3–4 предложения]

    💡 Совет дня:
    [1 предложение]

    🔢 Число дня:
    [1–99]

    🎨 Цвет дня:
    [цвет]
""").strip()

# --- 3 стратегии обращения по имени (без готовых падежей в данных) ---

SYSTEM_N1 = SYSTEM_BASE + dedent("""

    Обращение по имени:
    - Имя пользователя дано в именительном падеже.
    - Используй имя 1–2 раза за весь ответ.
    - Склоняй имя по правилам русского языка (Марина → Марине, Дмитрий → Дмитрию).
    - Глаголы и прилагательные — по полу из данных.
    - Без уменьшительных (Мариночка, Димочка).
""").strip()

SYSTEM_N2 = SYSTEM_BASE + dedent("""

    Обращение:
    - Начни прогноз с личного обращения: имя в нужном падеже + «, сегодня…»
      (как в живой речи: «Марине, сегодня…», «Аиду, сегодня…»).
    - Имя дано в именительном — сам выбери падеж по грамматике предложения.
    - Учитывай пол для форм глаголов (мужской/женский).
    - Имя больше 1–2 раз не повторяй — дальше «ты».
""").strip()

SYSTEM_N3 = SYSTEM_BASE + dedent("""

    Стиль обращения — как астролог на консультации:
    - По имени 1 раз в начале (дательный падеж: кому? — «…, сегодня»).
    - Остальной текст — на «ты», без повторения имени.
    - Имя только из данных, в правильном падеже по нормам русского.
    - Пол влияет на окончания глаголов и прилагательных.
""").strip()


@dataclass(frozen=True)
class Person:
    label: str
    profile: Profile
    lat: float
    lon: float
    gender: str
    target: date


def build_user(ctx, person: Person, chart) -> str:
    name = (person.profile.display_name or "").strip() or "друг"
    transits = [
        {
            "transit": t.transit_planet,
            "aspect": t.aspect,
            "natal": t.natal_planet,
            "orb": t.orb_deg,
        }
        for t in ctx.transits
    ]
    return dedent(f"""
        Прогноз на {ctx.date.isoformat()}.

        Имя: {name}
        Пол: {GENDER_RU[person.gender]}

        Натал: Солнце {chart.sun_sign}, Луна {chart.moon_sign or "—"}, ASC {chart.asc_sign or "—"}

        Транзиты:
        {json.dumps(transits, ensure_ascii=False, indent=2)}
    """).strip()


VARIANTS = [
    ("N1 — правила склонения", SYSTEM_N1),
    ("N2 — обращение в начале", SYSTEM_N2),
    ("N3 — консультация", SYSTEM_N3),
]

PEOPLE = [
    Person(
        "Марина (ж)",
        Profile(
            display_name="Марина",
            birth_date=date(1994, 7, 23),
            birth_time=datetime(1994, 7, 23, 8, 45, tzinfo=ZoneInfo("Europe/Moscow")),
            birth_place="Москва",
            city="Москва",
            timezone="Europe/Moscow",
        ),
        55.75,
        37.62,
        "femn",
        date(2026, 6, 12),
    ),
    Person(
        "Аид (м)",
        Profile(
            display_name="Аид",
            birth_date=date(1998, 3, 15),
            birth_time=datetime(1998, 3, 15, 14, 30, tzinfo=ZoneInfo("Europe/Moscow")),
            birth_place="Казань",
            city="Москва",
            timezone="Europe/Moscow",
        ),
        55.79,
        49.12,
        "masc",
        date(2026, 6, 12),
    ),
    Person(
        "Дмитрий (м)",
        Profile(
            display_name="Дмитрий",
            birth_date=date(1988, 11, 8),
            birth_time=datetime(1988, 11, 8, 6, 15, tzinfo=ZoneInfo("Europe/Moscow")),
            birth_place="Санкт-Петербург",
            city="Санкт-Петербург",
            timezone="Europe/Moscow",
        ),
        59.93,
        30.36,
        "masc",
        date(2026, 6, 13),
    ),
]


def generate(system: str, user: str) -> str:
    payload = {
        "model": "gemma4:e2b",
        "think": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": 0.78, "num_predict": 400, "num_ctx": 8192},
    }
    r = httpx.post("http://localhost:11434/api/chat", json=payload, timeout=300)
    r.raise_for_status()
    return (r.json().get("message") or {}).get("content", "").strip()


if __name__ == "__main__":
    for vlabel, system in VARIANTS:
        print("\n" + "#" * 70)
        print(f"# {vlabel}")
        print("#" * 70)
        for person in PEOPLE:
            chart = build_natal_chart(
                person.profile,
                lat=person.lat,
                lon=person.lon,
                timezone=person.profile.timezone,
            )
            ctx = build_daily_context(person.profile, chart, person.target)
            user = build_user(ctx, person, chart)
            cleaned = sanitize_prediction_output(generate(system, user))
            print(f"\n--- {person.label} | имя: {person.profile.display_name} ---")
            print(cleaned)
            print(f"[{len(cleaned)} символов]")
