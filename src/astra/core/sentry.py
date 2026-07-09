"""Инициализация Sentry для API, воркера и фоновых задач."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import sentry_sdk
from sentry_sdk.crons import capture_checkin
from sentry_sdk.crons.consts import MonitorStatus
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from astra.core.observability import Event, get_logger

if TYPE_CHECKING:
    from astra.core.config import Settings

log = get_logger(__name__)

_INITIALIZED = False

# Транзакции по этим путям не сэмплируются: пинги мониторинга — мусор в квоте.
_UNTRACED_PATHS = frozenset({"/health", "/metrics"})


def _make_traces_sampler(base_rate: float):
    def traces_sampler(sampling_context: dict[str, Any]) -> float:
        asgi_scope = sampling_context.get("asgi_scope") or {}
        if asgi_scope.get("path") in _UNTRACED_PATHS:
            return 0.0
        return base_rate

    return traces_sampler


def _build_integrations(service: str) -> list[object]:
    integrations: list[object] = [
        AsyncioIntegration(),
        HttpxIntegration(),
        LoggingIntegration(
            level=logging.INFO,
            event_level=logging.ERROR,
        ),
    ]
    if service == "api":
        integrations.extend(
            [
                FastApiIntegration(transaction_style="endpoint"),
                StarletteIntegration(transaction_style="endpoint"),
            ],
        )
    return integrations


def init_sentry(settings: Settings) -> None:
    """Подключить Sentry, если задан DSN и включён флаг."""
    global _INITIALIZED
    if _INITIALIZED or sentry_sdk.is_initialized():
        return
    if not settings.sentry_enabled:
        log.debug(Event.SENTRY_DISABLED, reason="flag_false")
        return
    if not settings.sentry_dsn:
        log.debug(Event.SENTRY_DISABLED, reason="empty_dsn")
        return

    service = settings.sentry_service.strip().lower() or "api"
    release = settings.sentry_release or f"astra@{settings.app_version}"

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        release=release,
        server_name=f"astra-{service}",
        send_default_pii=settings.sentry_send_default_pii,
        traces_sampler=_make_traces_sampler(settings.sentry_traces_sample_rate),
        profiles_sample_rate=settings.sentry_profiles_sample_rate,
        integrations=_build_integrations(service),
    )
    sentry_sdk.set_tag("service", service)
    _INITIALIZED = True
    log.info(
        Event.SENTRY_ENABLED,
        environment=settings.sentry_environment,
        service=service,
    )


def capture_exception(exc: BaseException) -> None:
    if sentry_sdk.is_initialized():
        sentry_sdk.capture_exception(exc)


def set_sentry_user(telegram_id: int | None) -> None:
    """Привязать события текущего scope к пользователю — даёт «users affected»."""
    if not sentry_sdk.is_initialized():
        return
    if telegram_id is None:
        sentry_sdk.set_user(None)
    else:
        sentry_sdk.set_user({"id": str(telegram_id)})


async def run_heartbeat(settings: Settings) -> None:
    """Периодический check-in в Sentry Crons.

    Замена uptime-монитору для прода без статического IP: Sentry не может
    достучаться до нас, поэтому мы сами пингуем Sentry. Пропущенный check-in
    (процесс умер, сервер без сети) создаёт issue и алерт.
    """
    slug = (settings.sentry_heartbeat_slug or "").strip()
    if not slug or not sentry_sdk.is_initialized():
        return

    interval_min = max(1, settings.sentry_heartbeat_interval_minutes)
    # Монитор создаётся/обновляется в Sentry автоматически при первом check-in.
    monitor_config = {
        "schedule": {"type": "interval", "value": interval_min, "unit": "minute"},
        "checkin_margin": max(2, interval_min),
        "max_runtime": interval_min,
        "failure_issue_threshold": 1,
        "recovery_threshold": 1,
    }
    log.info(Event.SENTRY_HEARTBEAT_STARTED, slug=slug, interval_minutes=interval_min)
    while True:
        capture_checkin(
            monitor_slug=slug,
            status=MonitorStatus.OK,
            monitor_config=monitor_config,
        )
        await asyncio.sleep(interval_min * 60)
