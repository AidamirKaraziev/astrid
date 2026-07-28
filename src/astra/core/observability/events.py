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
    TELEGRAM_BOT_BLOCKED = "telegram.bot_blocked"
    TELEGRAM_BOT_UNBLOCKED = "telegram.bot_unblocked"
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

    # Сохранённые натальные профили («Мои люди»)
    NATAL_PROFILE_UPDATED = "natal_profile.updated"
    NATAL_PROFILE_DELETED = "natal_profile.deleted"
    NATAL_PROFILE_PICKED = "natal_profile.picked"

    # Tarot
    TAROT_CARD_DRAWN = "tarot.card_drawn"
    TAROT_LIMIT_HIT = "tarot.limit_hit"
    TAROT_INTERPRET_FAILED = "tarot.interpret_failed"

    # Карта дня (бесплатный ежедневный продукт)
    DAY_CARD_SENT = "day_card.sent"
    DAY_CARD_FORECAST_SENT = "day_card.forecast_sent"
    DAY_CARD_FORECAST_FAILED = "day_card.forecast_failed"

    # Tarot readings pipeline (платные расклады)
    TAROT_READING_CREATED = "tarot_reading.created"
    TAROT_READING_GENERATED = "tarot_reading.generated"
    TAROT_READING_SENT = "tarot_reading.sent"
    TAROT_READING_FAILED = "tarot_reading.failed"
    TAROT_READING_FREE_GRANTED = "tarot_reading.free_granted"

    # Спроси Астрид (ответы по натальной карте)
    ASK_ANSWER_CREATED = "ask_answer.created"
    ASK_ANSWER_COMPUTED = "ask_answer.computed"
    ASK_ANSWER_GENERATED = "ask_answer.generated"
    ASK_ANSWER_SENT = "ask_answer.sent"
    ASK_ANSWER_FAILED = "ask_answer.failed"
    ASK_ANSWER_FROM_ARCHIVE = "ask_answer.from_archive"

    # Колесо фортуны
    WHEEL_SPIN = "wheel.spin"
    WHEEL_POOL_EMPTY = "wheel.pool_empty"
    WHEEL_FREE_SPIN_DUPLICATE = "wheel.free_spin_duplicate"
    WHEEL_PRIZE_ACTIVATED = "wheel.prize_activated"
    WHEEL_PRIZE_UNAVAILABLE = "wheel.prize_unavailable"
    WHEEL_ANIMATION_FAILED = "wheel.animation_failed"

    # Payments (Telegram Stars) — воронка: invoice_sent → completed
    PAYMENT_INVOICE_SENT = "payment.invoice_sent"
    PAYMENT_PRE_CHECKOUT_REJECTED = "payment.pre_checkout_rejected"
    PAYMENT_COMPLETED = "payment.completed"
    PAYMENT_DUPLICATE = "payment.duplicate"
    PAYMENT_ORPHAN = "payment.orphan"
    PAYMENT_REFUNDED = "payment.refunded"
    PAYMENT_REFUND_FAILED = "payment.refund_failed"

    # Служба заботы (релей обращений через админ-группу)
    SUPPORT_TICKET_CREATED = "support.ticket_created"
    SUPPORT_TICKET_CARD_FAILED = "support.ticket_card_failed"
    SUPPORT_REPLY_DELIVERED = "support.reply_delivered"
    SUPPORT_REPLY_DELIVER_FAILED = "support.reply_deliver_failed"

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
    LLM_DAILY_PROVIDER_UNCONFIGURED = "llm.daily_provider_unconfigured"
    RABBITMQ_RECONNECT = "rabbitmq.reconnect"

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
    SENTRY_HEARTBEAT_STARTED = "sentry.heartbeat.started"
