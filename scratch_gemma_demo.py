"""Одноразовый ресёрч-скрипт: реальный промпт Astrid → локальная Ollama.

Не часть проекта, удалить после исследования.
Запуск: .venv/bin/python scratch_gemma_demo.py <model> [num_ctx]
"""

import sys
import time as time_mod
import warnings
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

warnings.filterwarnings("ignore", category=DeprecationWarning)

# Регистрация всех мапперов SQLAlchemy, иначе relationship('NatalChart') не резолвится
import astra.astro.models  # noqa: F401
import astra.places.models  # noqa: F401
import astra.points.models  # noqa: F401
import astra.predictions.models  # noqa: F401
import astra.referrals.models  # noqa: F401

from astra.astro.calculator import build_natal_chart
from astra.astro.transits import build_daily_context
from astra.llm.prompts.astrid import (
    build_system_prompt,
    build_user_message,
    sanitize_prediction_output,
)
from astra.users.models import Profile

MODEL = sys.argv[1] if len(sys.argv) > 1 else "gemma4:latest"
NUM_CTX = int(sys.argv[2]) if len(sys.argv) > 2 else 8192

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

system = build_system_prompt()
user = build_user_message(ctx, profile, chart)

print(f"=== МОДЕЛЬ: {MODEL} | num_ctx={NUM_CTX} ===")
print(f"Натал: Солнце={chart.sun_sign}, Луна={chart.moon_sign}, ASC={chart.asc_sign}")
print(f"Транзиты на 2026-06-12: {len(ctx.transits)} шт.")
for t in ctx.transits:
    print(f"  {t.transit_planet} {t.aspect} {t.natal_planet} (orb {t.orb_deg}) — {t.theme}")
print()

payload = {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ],
    "stream": False,
    "options": {
        "temperature": 0.78,
        "num_predict": 450,
        "num_ctx": NUM_CTX,
    },
}

start = time_mod.monotonic()
resp = httpx.post("http://localhost:11434/api/chat", json=payload, timeout=600)
resp.raise_for_status()
data = resp.json()
elapsed = time_mod.monotonic() - start

raw = (data.get("message") or {}).get("content", "").strip()
eval_count = data.get("eval_count", 0)
eval_dur_s = data.get("eval_duration", 0) / 1e9 or 1
print(f"--- ГЕНЕРАЦИЯ: {elapsed:.1f}s всего, {eval_count} токенов, "
      f"{eval_count / eval_dur_s:.1f} t/s ---\n")
print("=== RAW ОТВЕТ ===")
print(raw)
print()
print("=== ПОСЛЕ sanitize_prediction_output ===")
print(sanitize_prediction_output(raw, prediction_date=ctx.date, sun_sign=chart.sun_sign))
