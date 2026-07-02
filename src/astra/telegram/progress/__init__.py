"""Прогресс генерации в Telegram: delete → новое сообщение."""

from astra.telegram.progress.messages import (
    compatibility_stage_text,
    prediction_stage_text,
)
from astra.telegram.progress.notifier import (
    advance_progress,
    clear_progress,
    current_progress_message_id,
    notify_compatibility_stage,
    notify_prediction_stage,
)
from astra.telegram.progress.stages import (
    CompatibilityStage,
    PredictionStage,
    compatibility_job_key,
    prediction_job_key,
)
from astra.telegram.progress.store import (
    clear_progress_message_id,
    get_progress_message_id,
    progress_redis_key,
    set_progress_message_id,
)

__all__ = [
    "CompatibilityStage",
    "PredictionStage",
    "advance_progress",
    "clear_progress",
    "clear_progress_message_id",
    "compatibility_job_key",
    "compatibility_stage_text",
    "current_progress_message_id",
    "get_progress_message_id",
    "notify_compatibility_stage",
    "notify_prediction_stage",
    "prediction_job_key",
    "prediction_stage_text",
    "progress_redis_key",
    "set_progress_message_id",
]
