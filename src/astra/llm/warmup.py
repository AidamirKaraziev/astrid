"""Прогрев модели Ollama при старте воркера."""

from __future__ import annotations

import httpx

from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger

log = get_logger(__name__)


async def warmup_ollama_model(settings: Settings | None = None) -> None:
    """Загрузить модель в RAM до первого пользовательского запроса."""
    cfg = settings or get_settings()
    if not cfg.ollama_enabled:
        log.info(Event.OLLAMA_WARMUP_SKIPPED, reason="disabled")
        return

    url = f"{cfg.ollama_base_url.rstrip('/')}/api/chat"
    payload = {
        "model": cfg.ollama_model,
        "think": False,
        "keep_alive": "30m",
        "messages": [{"role": "user", "content": "ok"}],
        "stream": False,
        "options": {"num_predict": 1},
    }
    try:
        async with httpx.AsyncClient(timeout=cfg.ollama_timeout_seconds) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
    except Exception:
        log.exception(
            Event.OLLAMA_WARMUP_FAILED,
            model=cfg.ollama_model,
            base_url=cfg.ollama_base_url,
        )
        return

    log.info(Event.OLLAMA_WARMUP_OK, model=cfg.ollama_model)
