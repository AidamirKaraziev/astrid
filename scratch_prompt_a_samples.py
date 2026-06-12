"""3 прогноза: промпт A + имя + пол → gemma4:e2b."""

import json
import warnings
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
from astra.text.ru_inflect import format_name_cases, inflect_name
from astra.users.models import Profile

MORPH = MorphAnalyzer()

PROMPT_A = dedent("""
    Ты — Astrid, голос Telegram-бота Astra. Пишешь короткий персональный прогноз на день.

    Правила:
    - Только русский (кириллица), обращение на «ты».
    - Опирайся на натал и transits из сообщения; не выдумывай аспекты.
    - Сильнее влияют транзиты с меньшим orb_deg.
    - Обращайся по имени 1–2 раза за весь ответ; склоняй по падежам (данные в сообщении).
    - Учитывай пол пользователя из данных: для мужчин — мужские формы глаголов и прилагательных
      (готов, уверен, смел); для женщин — женские (готова, уверена, смела). Без уменьшительных имён.
    - Мягкие формулировки, без запугивания и пустых фраз из журнала.
    - Не используй: ритм, гармония, трансформация, вибрации, энергетика.

    Формат ответа (строго):

    ✨ Прогноз дня

    [3–4 предложения: эмоции, отношения, работа, самочувствие — один абзац]

    💡 Совет дня:
    [1 предложение]

    🔢 Число дня:
    [число 1–99]

    🎨 Цвет дня:
    [цвет]
""").strip()

GENDER_RU = {"masc": "мужской", "femn": "женский", "neut": "нейтральный"}


def detect_gender(name: str) -> str:
    word = name.strip().split()[0] if name.strip() else ""
    if not word:
        return "не указан"
    parsed = MORPH.parse(word)
    if not parsed:
        return "не указан"
    g = parsed[0].tag.gender
    return GENDER_RU.get(g, "не указан")


def build_user(ctx, profile, chart) -> str:
    name = (profile.display_name or "").strip() or "друг"
    gender = detect_gender(name)
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
    return dedent(f"""
        Имя: {name}
        Пол: {gender}
        Склонения имени: {format_name_cases(name)}
        Пример обращения: «{inflect_name(name, "datv")}, сегодня…»
        Дата прогноза: {ctx.date.isoformat()}
        Натал: Солнце {chart.sun_sign}, Луна {chart.moon_sign or "—"}, ASC {chart.asc_sign or "—"}
        Точность профиля: {chart.accuracy_tier}%

        Транзиты сегодня (JSON):
        {json.dumps(transits, ensure_ascii=False, indent=2)}
    """).strip()


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


CASES = [
    {
        "label": "1 — Марина (ж)",
        "profile": Profile(
            display_name="Марина",
            birth_date=date(1994, 7, 23),
            birth_time=datetime(1994, 7, 23, 8, 45, tzinfo=ZoneInfo("Europe/Moscow")),
            birth_place="Москва",
            city="Москва",
            timezone="Europe/Moscow",
        ),
        "lat": 55.75,
        "lon": 37.62,
        "target": date(2026, 6, 12),
    },
    {
        "label": "2 — Аид (м)",
        "profile": Profile(
            display_name="Аид",
            birth_date=date(1998, 3, 15),
            birth_time=datetime(1998, 3, 15, 14, 30, tzinfo=ZoneInfo("Europe/Moscow")),
            birth_place="Казань",
            city="Москва",
            timezone="Europe/Moscow",
        ),
        "lat": 55.79,
        "lon": 49.12,
        "target": date(2026, 6, 12),
    },
    {
        "label": "3 — Дмитрий (м)",
        "profile": Profile(
            display_name="Дмитрий",
            birth_date=date(1988, 11, 8),
            birth_time=datetime(1988, 11, 8, 6, 15, tzinfo=ZoneInfo("Europe/Moscow")),
            birth_place="Санкт-Петербург",
            city="Санкт-Петербург",
            timezone="Europe/Moscow",
        ),
        "lat": 59.93,
        "lon": 30.36,
        "target": date(2026, 6, 13),
    },
]

for case in CASES:
    p = case["profile"]
    chart = build_natal_chart(p, lat=case["lat"], lon=case["lon"], timezone=p.timezone)
    ctx = build_daily_context(p, chart, case["target"])
    user_msg = build_user(ctx, p, chart)
    raw = generate(PROMPT_A, user_msg)
    cleaned = sanitize_prediction_output(raw)
    print("=" * 64)
    print(f"ПРИМЕР {case['label']}")
    print(f"Натал: {chart.sun_sign} / {chart.moon_sign} / ASC {chart.asc_sign}")
    print(f"Пол в промпте: {detect_gender(p.display_name)}")
    print("=" * 64)
    print(cleaned)
    print(f"\n[{len(cleaned)} символов]\n")
