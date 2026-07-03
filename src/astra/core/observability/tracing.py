"""OpenTelemetry: traces, propagation, span helpers."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opentelemetry.trace import Span, Tracer

_OTEL_CONFIGURED = False


def is_otel_enabled() -> bool:
    return _OTEL_CONFIGURED


def configure_otel(settings: Any) -> None:
    """Инициализировать OTel TracerProvider и Sentry span processor."""
    global _OTEL_CONFIGURED
    if _OTEL_CONFIGURED or not settings.otel_enabled:
        return

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
    from sentry_sdk.integrations.opentelemetry import SentryPropagator, SentrySpanProcessor, setup_sentry_propagation

    service = (settings.sentry_service or "api").strip().lower()
    resource = Resource.create(
        {
            "service.name": f"astra-{service}",
            "service.version": settings.app_version,
        },
    )
    sampler = ParentBased(TraceIdRatioBased(settings.otel_traces_sample_rate))
    provider = TracerProvider(resource=resource, sampler=sampler)
    provider.add_span_processor(SentrySpanProcessor())
    trace.set_tracer_provider(provider)

    setup_sentry_propagation()
    from opentelemetry.propagate import set_global_textmap

    set_global_textmap(SentryPropagator())
    _OTEL_CONFIGURED = True


def instrument_httpx(settings: Any) -> None:
    if not settings.otel_enabled:
        return
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument()


def instrument_fastapi_app(settings: Any, app: Any) -> None:
    if not settings.otel_enabled:
        return
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)


def instrument_sqlalchemy_engine(settings: Any) -> None:
    if not settings.otel_enabled:
        return
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        from astra.db.session import get_engine

        SQLAlchemyInstrumentor().instrument(engine=get_engine().sync_engine)
    except Exception:
        pass


def get_tracer(name: str) -> Tracer:
    from opentelemetry import trace

    return trace.get_tracer(name)


def inject_trace_context(carrier: dict[str, Any]) -> None:
    if not _OTEL_CONFIGURED:
        return
    from opentelemetry.propagate import inject

    inject(carrier)


def extract_trace_context(carrier: dict[str, Any] | None) -> Any | None:
    if not _OTEL_CONFIGURED or not carrier:
        return None
    from opentelemetry import context as otel_context
    from opentelemetry.propagate import extract

    return otel_context.attach(extract(carrier))


def detach_trace_context(token: Any | None) -> None:
    if token is None:
        return
    from opentelemetry import context as otel_context

    otel_context.detach(token)


@contextmanager
def start_span(name: str, **attributes: Any):
    if not _OTEL_CONFIGURED:
        yield None
        return

    tracer = get_tracer("astra")
    with tracer.start_as_current_span(name, attributes=attributes) as span:
        yield span
