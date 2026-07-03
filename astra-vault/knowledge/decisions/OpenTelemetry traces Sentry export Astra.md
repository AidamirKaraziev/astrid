---
tags: [decision, observability, opentelemetry]
date: 2026-07-03
---

# OpenTelemetry traces Sentry export Astra

## Решение

- `OTEL_ENABLED=true` включает TracerProvider + `SentrySpanProcessor` + `SentryPropagator`.
- Auto-instrument: **httpx**, **FastAPI**, **SQLAlchemy** (после `init_engine`).
- Spans вручную: `worker.task`, `llm.complete` (через `TracingLlmProvider`).
- Propagation: W3C traceparent через AMQP headers при publish/consume (вместе с `x-correlation-id`).
- Логи получают `trace_id` / `span_id` через processor `add_trace_context`.

## Конфиг

```env
OTEL_ENABLED=false          # true на prod когда готов Sentry Performance
OTEL_TRACES_SAMPLE_RATE=0.1 # dev: 1.0
```

## Связи

- [[structured logging structlog и event taxonomy Astra]]
- [[correlation_id propagation через RabbitMQ и Telegram]]
- [[Sentry environment local dev prod и service api worker]]
