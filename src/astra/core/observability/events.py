"""Стабильные идентификаторы событий для structured logging."""

from enum import StrEnum


class Event(StrEnum):
    # Application lifecycle
    APP_STARTED = "app.started"
    APP_SHUTDOWN = "app.shutdown"

    # HTTP (FastAPI)
    HTTP_REQUEST_COMPLETED = "http.request.completed"

    # Telegram
    TELEGRAM_UPDATE_RECEIVED = "telegram.update.received"
    TELEGRAM_UPDATE_COMPLETED = "telegram.update.completed"
    TELEGRAM_UPDATE_FAILED = "telegram.update.failed"
    TELEGRAM_MESSAGE_SENT = "telegram.message.sent"
    TELEGRAM_PDF_SENT = "telegram.pdf.sent"
    TELEGRAM_POLLING_STARTED = "telegram.polling.started"
    TELEGRAM_POLLING_STOPPED = "telegram.polling.stopped"
    TELEGRAM_POLLING_ERROR = "telegram.polling.error"
    TELEGRAM_BOT_MENU_CONFIGURED = "telegram.bot_menu.configured"
    TELEGRAM_API_FAILED = "telegram.api.failed"
    TELEGRAM_PROGRESS_NOTIFY_FAILED = "telegram.progress.notify_failed"

    # Worker / RabbitMQ tasks
    TASK_RECEIVED = "task.received"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_SKIPPED = "task.skipped"
    TASK_PUBLISHED = "task.published"

    # Prediction pipeline
    PREDICTION_NATAL_STORED = "prediction.natal_stored"
    PREDICTION_CONTEXT_STORED = "prediction.context_stored"
    PREDICTION_GENERATED = "prediction.generated"
    PREDICTION_SENT = "prediction.sent"
    PREDICTION_ABANDONED = "prediction.abandoned"
    PREDICTION_RETRY = "prediction.retry"
    PREDICTION_GENERATION_FAILED = "prediction.generation_failed"
    PREDICTION_QUEUED = "prediction.queued"
    PREDICTION_DEDUP_HIT = "prediction.dedup_hit"
    PREDICTION_DELAYED_NOTIFY = "prediction.delayed_notify"
    PREDICTION_FINAL_FAILURE_NOTIFY = "prediction.final_failure_notify"

    # Compatibility pipeline
    COMPATIBILITY_SYNASTRY_STORED = "compatibility.synastry_stored"
    COMPATIBILITY_LLM_DONE = "compatibility.llm_done"
    COMPATIBILITY_LLM_ABANDONED = "compatibility.llm_abandoned"
    COMPATIBILITY_LLM_STEP_FAILED = "compatibility.llm_step_failed"
    COMPATIBILITY_ASSEMBLE_FAILED = "compatibility.assemble_failed"
    COMPATIBILITY_PDF_READY = "compatibility.pdf_ready"
    COMPATIBILITY_PDF_ABANDONED = "compatibility.pdf_abandoned"
    COMPATIBILITY_SENT = "compatibility.sent"
    COMPATIBILITY_REPORT_MISSING = "compatibility.report_missing"
    COMPATIBILITY_REPORT_CREATE_FAILED = "compatibility.report_create_failed"
    COMPATIBILITY_LLM_FAILED = "compatibility.llm_failed"
    COMPATIBILITY_PDF_FAILED = "compatibility.pdf_failed"
    COMPATIBILITY_NOTIFY_FAILED = "compatibility.notify_failed"

    # Tarot
    TAROT_CARD_DRAWN = "tarot.card_drawn"
    TAROT_LIMIT_HIT = "tarot.limit_hit"
    TAROT_INTERPRET_FAILED = "tarot.interpret_failed"

    # Natal report pipeline
    NATAL_REPORT_CREATED = "natal_report.created"
    NATAL_REPORT_LLM_DONE = "natal_report.llm_done"
    NATAL_REPORT_LLM_STEP_FAILED = "natal_report.llm_step_failed"
    NATAL_REPORT_ASSEMBLE_FAILED = "natal_report.assemble_failed"
    NATAL_REPORT_LLM_FAILED = "natal_report.llm_failed"
    NATAL_REPORT_PDF_READY = "natal_report.pdf_ready"
    NATAL_REPORT_PDF_FAILED = "natal_report.pdf_failed"
    NATAL_REPORT_SENT = "natal_report.sent"
    NATAL_REPORT_MISSING = "natal_report.missing"
    NATAL_REPORT_NOTIFY_FAILED = "natal_report.notify_failed"

    # Onboarding / user
    ONBOARDING_INVALID_DATA = "onboarding.invalid_data"
    ONBOARDING_REFERRAL_REWARD_FAILED = "onboarding.referral_reward_failed"
    ONBOARDING_REFERRAL_CODE_FAILED = "onboarding.referral_code_failed"
    GREETING_COMPLETED = "greeting.completed"
    NATAL_CHART_REFRESH_FAILED = "natal_chart.refresh_failed"

    # Integrations
    LLM_REQUEST = "llm.request"
    LLM_RESPONSE = "llm.response"
    LLM_HTTP_ERROR = "llm.http_error"
    LLM_VALIDATION_FAILED = "llm.validation_failed"
    RABBITMQ_RECONNECT = "rabbitmq.reconnect"
    OLLAMA_WARMUP_SKIPPED = "ollama.warmup_skipped"
    OLLAMA_WARMUP_OK = "ollama.warmup_ok"
    OLLAMA_WARMUP_FAILED = "ollama.warmup_failed"

    # GeoNames
    GEONAMES_DOWNLOAD = "geonames.download"
    GEONAMES_EXTRACTED = "geonames.extracted"
    GEONAMES_IMPORT_PROGRESS = "geonames.import_progress"
    GEONAMES_IMPORT_DONE = "geonames.import_done"
    GEONAMES_IMPORT_FAILED = "geonames.import_failed"

    # Redis
    REDIS_PROGRESS_CLEARED = "redis.progress_cleared"
    REDIS_PREDICTION_PENDING_CLEARED = "redis.prediction_pending_cleared"

    # Scheduler
    SCHEDULER_TICK = "scheduler.tick"
    SCHEDULER_ENQUEUED = "scheduler.enqueued"
    SCHEDULER_ITERATION_FAILED = "scheduler.iteration_failed"

    # Places
    PLACES_SEARCH_EMPTY = "places.search_empty"

    # Sentry
    SENTRY_ENABLED = "sentry.enabled"
    SENTRY_DISABLED = "sentry.disabled"
