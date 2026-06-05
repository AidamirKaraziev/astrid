"""Клиент Ollama для генерации ежедневного инсайта Astrid."""

from __future__ import annotations

import logging

import httpx

from astra.astro.schemas import AstroContext, NatalChartData
from astra.core.config import Settings, get_settings
from astra.users.models import Profile
from astra.llm.prompts.astrid import (
    build_system_prompt,
    build_user_message,
    sanitize_prediction_output,
)

logger = logging.getLogger(__name__)

_ASTRID_TEMPERATURE = 0.78
_ASTRID_NUM_PREDICT = 450


async def generate_prediction_body(
    ctx: AstroContext,
    profile: Profile,
    chart: NatalChartData,
    settings: Settings | None = None,
) -> str | None:
    """Сгенерировать текст инсайта на день; None — ошибка или пустой ответ."""
    cfg = settings or get_settings()
    payload = {
        "model": cfg.ollama_model,
        "messages": [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": build_user_message(ctx, profile, chart)},
        ],
        "stream": False,
        "options": {
            "temperature": _ASTRID_TEMPERATURE,
            "num_predict": _ASTRID_NUM_PREDICT,
        },
    }
    url = f"{cfg.ollama_base_url.rstrip('/')}/api/chat"
    try:
        async with httpx.AsyncClient(timeout=cfg.ollama_timeout_seconds) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception:
        logger.exception("Ollama request failed")
        return None

    message = data.get("message") or {}
    raw = (message.get("content") or "").strip()
    if not raw:
        return None

    cleaned = sanitize_prediction_output(raw)
    return cleaned or None
