"""Инициализация Sentry для API, воркера и фоновых задач."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

if TYPE_CHECKING:
    from astra.core.config import Settings

logger = logging.getLogger(__name__)

_INITIALIZED = False


def init_sentry(settings: Settings) -> None:
    """Подключить Sentry, если задан DSN и включён флаг."""
    global _INITIALIZED
    if _INITIALIZED or sentry_sdk.is_initialized():
        return
    if not settings.sentry_enabled:
        logger.debug("Sentry disabled (SENTRY_ENABLED=false)")
        return
    if not settings.sentry_dsn:
        logger.debug("Sentry skipped: SENTRY_DSN is empty")
        return

    release = settings.sentry_release or f"astra@{settings.app_version}"

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        release=release,
        send_default_pii=settings.sentry_send_default_pii,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        profiles_sample_rate=settings.sentry_profiles_sample_rate,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            StarletteIntegration(transaction_style="endpoint"),
            AsyncioIntegration(),
            HttpxIntegration(),
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR,
            ),
        ],
    )
    _INITIALIZED = True
    logger.info("Sentry enabled (environment=%s)", settings.sentry_environment)


def capture_exception(exc: BaseException) -> None:
    if sentry_sdk.is_initialized():
        sentry_sdk.capture_exception(exc)
