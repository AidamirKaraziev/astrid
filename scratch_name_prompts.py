"""3 промпта со стратегиями склонения имён → gemma4:e2b."""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from datetime import date, datetime
from textwrap import dedent
from zoneinfo import ZoneInfo

import httpx
from pymorphy3 import MorphAnalyzer

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

MORPH = MorphAnalyzer()

# Ручные формы для имён, которые pymorphy ломает
_NAME_OVERRIDES: dict[str, dict[str, str]] = {
    "аид": {
        "nomn": "Аид",
        "gent": "Аида",
        "datv": "Аиду",
        "accs": "Аида",
        "ablt": "Аидом",
        "loct": "Аиде",
    },
}

GENDER_RU = {"masc": "мужской", "femn": "женский"}


@dataclass(frozen=True)
class Person:
    label: str
    profile: Profile
    lat: float
    lon: float
    gender: str  # masc | femn
    target: date


def _first_name(name: str) -> str:
    return name.strip().split()[0] if name.strip() else name.strip()


def inflect_with_gender(name: str, case: str, gender: str) -> str:
    key = _first_name(name).lower()
    if key in _NAME_OVERRIDES and case in _NAME_OVERRIDES[key]:
        return _NAME_OVERRIDES[key][case]

    word = _first_name(name)
    parsed = MORPH.parse(word)
    if not parsed:
        return word
    tag = {"datv", gender} if gender in ("masc", "femn") else {case}
    if case != "datv":
        tag = {case, gender} if gender in ("masc", "femn") else {case}
    else:
        tag = {"datv", gender} if gender in ("masc", "femn") else {"datv"}

    for p in parsed:
        form = p.inflect(tag)
        if form is not None:
            w = form.word
            return w[:1].upper() + w[1:] if word[:1].isupper() else w
    form = parsed[0].inflect({case})
    if form is None:
        return word
    w = form.word
    return w[:1].upper() + w[1:] if word[:1].isupper() else w


def name_forms(name: str, gender: str) -> dict[str, str]:
    return {
        "именительный": _first_name(name),
        "родительный": inflect_with_gender(name, "gent", gender),
        "дательный": inflect_with_gender(name, "datv", gender),
        "винительный": inflect_with_gender(name, "accs", gender),
        "творительный": inflect_with_gender(name, "ablt", gender),
    }


def build_transits_json(ctx) -> str:
    transits = [
        {
            "transit": t.transit_planet,
            "aspect": t.aspect,
            "natal": t.natal_planet,
            "orb": t.orb_deg,
            "theme": t.theme,
        }
        for t in ctx.transits
    ]
    return json.dumps(transits, ensure_ascii=False, indent=2)


def build_user_d1(ctx, person: Person, chart, forms: dict[str, str]) -> str:
    gender_ru = GENDER_RU[person.gender]
    datv = forms["дательный"]
    gent = forms["родительный"]
    return dedent(f"""
        Составь прогноз на день.

        Имя (именительный): {forms["именительный"]}
        Пол: {gender_ru}

        СКОПИРУЙ ДОСЛОВНО одну из фраз для обращения (не меняй ни одной буквы):
        1) «{datv}, сегодня»
        2) «для {gent}»

        Дата: {ctx.date.isoformat()}
        Натал: Солнце {chart.sun_sign}, Луна {chart.moon_sign or "—"}, ASC {chart.asc_sign or "—"}

        Транзиты:
        {build_transits_json(ctx)}
    """).strip()


def build_user_d2(ctx, person: Person, chart, forms: dict[str, str]) -> str:
    gender_ru = GENDER_RU[person.gender]
    datv = forms["дательный"]
    return dedent(f"""
        Прогноз на сегодня.

        Имя: {forms["именительный"]} ({gender_ru})
        Дательный падеж: {datv}

        ПЕРВОЕ предложение прогноза ОБЯЗАТЕЛЬНО начни ровно так:
        «{datv}, сегодня»

        Дальше — только «ты/тебе/твой», имя больше не повторяй.
        Глаголы и прилагательные — по полу ({gender_ru}).

        Натал: Солнце {chart.sun_sign}, Луна {chart.moon_sign or "—"}, ASC {chart.asc_sign or "—"}
        Транзиты (orb меньше = сильнее):
        {build_transits_json(ctx)}
    """).strip()


def build_user_d3(ctx, person: Person, chart, forms: dict[str, str]) -> str:
    gender_ru = GENDER_RU[person.gender]
    datv = forms["дательный"]
    gent = forms["родительный"]
    verb_hint = (
        "готов/уверен/смел/занят"
        if person.gender == "masc"
        else "готова/уверена/смела/занята"
    )
    return dedent(f"""
        Данные для прогноза Astrid.

        Пользователь: {forms["именительный"]}, пол {gender_ru}.
        Разрешённые формы имени (только они, другие не придумывай):
        - дательный: {datv}
        - родительный: {gent}

        Правило обращения:
        - в блоке «Прогноз дня» имя используй РОВНО 1 раз — в первом предложении как «{datv}, …»
        - во всём остальном тексте — только «ты», без имени
        - глагольные формы: {verb_hint}

        {ctx.date.isoformat()} | {chart.sun_sign} / {chart.moon_sign or "—"} / ASC {chart.asc_sign or "—"}
        {build_transits_json(ctx)}
    """).strip()


SYSTEM_BASE = dedent("""
    Ты — Astrid, голос бота Astra. Короткий персональный прогноз на день.

    Общие правила:
    - Только русский, обращение на «ты».
    - Не выдумывай аспекты — только из transits.
    - Мягко, без запугивания и журнальных штампов.
    - Не используй: ритм, гармония, трансформация, вибрации, энергетика, внутренние процессы.

    Формат:

    ✨ Прогноз дня

    [3–4 предложения, один абзац]

    💡 Совет дня:
    [1 предложение]

    🔢 Число дня:
    [1–99]

    🎨 Цвет дня:
    [цвет]
""").strip()

SYSTEM_D1 = SYSTEM_BASE + "\n\nИмена: используй ТОЛЬКО готовые фразы из сообщения пользователя, символ в символ."

SYSTEM_D2 = SYSTEM_BASE + "\n\nИмена: первое предложение — строго по шаблону из сообщения; имя в других падежах не используй."

SYSTEM_D3 = SYSTEM_BASE + "\n\nИмена: одно обращение в дательном падеже в первом предложении, дальше без имени."


VARIANTS = [
    ("D1 — дословные фразы", SYSTEM_D1, build_user_d1),
    ("D2 — шаблон первой фразы", SYSTEM_D2, build_user_d2),
    ("D3 — одно обращение", SYSTEM_D3, build_user_d3),
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
    for vlabel, system, user_builder in VARIANTS:
        print("\n" + "#" * 70)
        print(f"# ПРОМПТ {vlabel}")
        print("#" * 70)
        for person in PEOPLE:
            chart = build_natal_chart(
                person.profile,
                lat=person.lat,
                lon=person.lon,
                timezone=person.profile.timezone,
            )
            ctx = build_daily_context(person.profile, chart, person.target)
            forms = name_forms(person.profile.display_name, person.gender)
            user = user_builder(ctx, person, chart, forms)
            raw = generate(system, user)
            cleaned = sanitize_prediction_output(raw)
            print(f"\n--- {person.label} | дательный: {forms['дательный']} ---")
            print(cleaned)
            print(f"[{len(cleaned)} символов]")
