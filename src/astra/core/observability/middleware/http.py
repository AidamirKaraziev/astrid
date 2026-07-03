"""FastAPI HTTP request lifecycle logging."""

from __future__ import annotations

import time
from collections.abc import Callable
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from astra.core.observability.context import bound_context
from astra.core.observability.events import Event
from astra.core.observability.logging import get_logger

log = get_logger(__name__)


class HttpObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        correlation_id = (
            request.headers.get("x-correlation-id")
            or request.headers.get("x-request-id")
            or f"http-{uuid4().hex[:12]}"
        )
        path = request.url.path
        is_health = path == "/health"

        with bound_context(correlation_id=correlation_id):
            started = time.perf_counter()
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - started) * 1000)

            if is_health:
                log.debug(
                    Event.HTTP_REQUEST_COMPLETED,
                    method=request.method,
                    path=path,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
            else:
                log.info(
                    Event.HTTP_REQUEST_COMPLETED,
                    method=request.method,
                    path=path,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
            return response
