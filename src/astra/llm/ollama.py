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

_ASTRID_TEMPERATURE = 0.72
_ASTRID_NUM_PREDICT = 380
_ASTRID_NUM_CTX = 4096


async def generate_prediction_body(
    ctx: AstroContext,
    profile: Profile,
    chart: NatalChartData,
    settings: Settings | None = None,
) -> tuple[str | None, str]:
    """Сгенерировать текст инсайта на день; (None, reason) — ошибка или пустой ответ."""
    cfg = settings or get_settings()
    payload = {
        "model": cfg.ollama_model,
        "think": False,
        "keep_alive": "30m",
        "messages": [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": build_user_message(ctx, profile, chart)},
        ],
        "stream": False,
        "options": {
            "temperature": _ASTRID_TEMPERATURE,
            "num_predict": _ASTRID_NUM_PREDICT,
            "num_ctx": _ASTRID_NUM_CTX,
        },
    }
    url = f"{cfg.ollama_base_url.rstrip('/')}/api/chat"
    try:
        async with httpx.AsyncClient(timeout=cfg.ollama_timeout_seconds) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        logger.warning("Ollama request timed out")
        return None, "timeout"
    except httpx.ConnectError:
        logger.warning("Ollama connection failed")
        return None, "connection"
    except httpx.HTTPStatusError as exc:
        logger.warning("Ollama HTTP error: %s", exc.response.status_code)
        return None, f"http_{exc.response.status_code}"
    except Exception:
        logger.exception("Ollama request failed")
        return None, "request_error"

    message = data.get("message") or {}
    raw = (message.get("content") or "").strip()
    if not raw:
        return None, "empty_response"

    cleaned = sanitize_prediction_output(
        raw,
        prediction_date=ctx.date,
        sun_sign=chart.sun_sign,
    )
    if not cleaned:
        return None, "sanitize_empty"
    return cleaned, ""
