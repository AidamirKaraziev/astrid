"""Прогрев модели Ollama при старте воркера."""

from __future__ import annotations

import logging

import httpx

from astra.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


async def warmup_ollama_model(settings: Settings | None = None) -> None:
    """Загрузить модель в RAM до первого пользовательского запроса."""
    cfg = settings or get_settings()
    if not cfg.ollama_enabled:
        logger.info("Ollama warmup skipped: OLLAMA_ENABLED=false")
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
        logger.exception(
            "Ollama warmup failed for model %s at %s",
            cfg.ollama_model,
            cfg.ollama_base_url,
        )
        return

    logger.info("Ollama warmup OK: model=%s", cfg.ollama_model)
