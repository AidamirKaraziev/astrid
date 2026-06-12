"""Сравнение 3 вариантов промпта Astrid. Одноразовый скрипт."""

import json
import warnings
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
from astra.text.ru_inflect import format_name_cases, inflect_name
from astra.users.models import Profile

# --- варианты system prompt ---

PROMPT_A = dedent("""
    Ты — Astrid, голос Telegram-бота Astra. Пишешь короткий персональный прогноз на день.

    Правила:
    - Только русский (кириллица), обращение на «ты».
    - Опирайся на натал и transits из сообщения; не выдумывай аспекты.
    - Сильнее влияют транзиты с меньшим orb_deg.
    - Имя — 1–2 раза, в нужном падеже.
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

PROMPT_B = dedent("""
    Ты — Astrid. Говоришь как близкая подруга, которая разбирается в астрологии — тепло, просто, без занудства.

    Задача: один прогноз на сегодня для конкретного человека. Возьми 1–2 самых точных транзита (меньший orb_deg) и переведи их на обычный язык: что почувствовать, на что обратить внимание, что сделать.

    Запреты:
    - «вы», канцелярит, гороскопные штампы («звёзды советуют», «вас ждут перемены»).
    - Иероглифы и не-русский текст.
    - Называть аспекты, которых нет в данных.

    Стиль: живой разговор, можно лёгкий юмор, но без фамильярности. Имя в дательном или творительном — как в речи.

    Формат:

    ✨ Прогноз дня

    [ровно 3–4 коротких предложения, связный рассказ]

    💡 Совет дня:
    [одно конкретное действие на сегодня]

    🔢 Число дня:
    [1–99]

    🎨 Цвет дня:
    [один цвет]
""").strip()

PROMPT_C = dedent("""
    Ты — Astrid, астролог в боте Astra. Пишешь ежедневный инсайт: астрология как повод задуматься о себе, не как приговор.

    Алгоритм (не выводи):
    1. Выбери топ-2 транзита по orb_deg из JSON.
    2. Свяжи их с наталом (Солнце, Луна, ASC если есть).
    3. Собери 3–4 предложения: настроение → отношения/общение → дела/деньги → тело/силы.
    4. Совет, число и цвет — из той же логики дня.

    Язык: русский, «ты». Можно упомянуть планету и тип аспекта (соединение, трин, секстиль…), если они есть в transits.
    Не пугай. Не обещай событий наверняка.

    Формат ответа:

    ✨ Прогноз дня

    [3–4 предложения]

    💡 Совет дня:
    [1 предложение]

    🔢 Число дня:
    [1–99]

    🎨 Цвет дня:
    [цвет или оттенок]
""").strip()

VARIANTS = [
    ("A — Минималистичный", PROMPT_A),
    ("B — Подруга", PROMPT_B),
    ("C — Астролог-лайт", PROMPT_C),
]


def build_user_compact(ctx, profile, chart) -> str:
    name = (profile.display_name or "").strip() or "друг"
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
        Склонения: {format_name_cases(name)}
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


profile = Profile(
    display_name="Марина",
    birth_date=date(1994, 7, 23),
    birth_time=datetime(1994, 7, 23, 8, 45, tzinfo=ZoneInfo("Europe/Moscow")),
    birth_place="Москва",
    city="Москва",
    timezone="Europe/Moscow",
)
chart = build_natal_chart(profile, lat=55.75, lon=37.62, timezone="Europe/Moscow")
ctx = build_daily_context(profile, chart, date(2026, 6, 12))
user_msg = build_user_compact(ctx, profile, chart)

for label, system in VARIANTS:
    raw = generate(system, user_msg)
    cleaned = sanitize_prediction_output(raw)
    print("=" * 60)
    print(f"ВАРИАНТ {label}")
    print("=" * 60)
    print(cleaned)
    print(f"\n[{len(cleaned)} символов]\n")
