"""Уведомления прогресса: delete → typing → send → save message_id."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from astra.core.config import Settings
from astra.core.observability import Event, get_logger
from astra.telegram.progress.api import (
    delete_message,
    send_chat_action_typing,
    send_html_message,
)
from astra.telegram.progress.messages import (
    compatibility_stage_text,
    natal_stage_text,
    prediction_stage_text,
)
from astra.telegram.progress.stages import (
    CompatibilityStage,
    NatalStage,
    PredictionStage,
    compatibility_job_key,
    natal_job_key,
    prediction_job_key,
)
from astra.telegram.progress.store import (
    clear_progress_message_id,
    get_progress_message_id,
    set_progress_message_id,
)

log = get_logger(__name__)


async def advance_progress(
    chat_id: int,
    user_id: UUID,
    job_key: str,
    text: str,
    *,
    with_typing: bool = True,
    settings: Settings | None = None,
) -> int | None:
    """Удалить предыдущее progress-сообщение и отправить новое."""
    previous_id = await get_progress_message_id(user_id, job_key)
    if previous_id is not None:
        await delete_message(chat_id, previous_id, settings=settings)

    if with_typing:
        await send_chat_action_typing(chat_id, settings=settings)

    message_id = await send_html_message(chat_id, text, settings=settings)
    if message_id is None:
        log.warning(
            Event.TELEGRAM_PROGRESS_NOTIFY_FAILED,
            chat_id=chat_id,
            user_id=user_id,
            job_key=job_key,
        )
        return None

    await set_progress_message_id(user_id, job_key, message_id)
    return message_id


async def clear_progress(
    chat_id: int,
    user_id: UUID,
    job_key: str,
    *,
    settings: Settings | None = None,
) -> None:
    """Убрать progress-сообщение из чата и Redis (перед финальной доставкой)."""
    previous_id = await clear_progress_message_id(user_id, job_key)
    if previous_id is not None:
        await delete_message(chat_id, previous_id, settings=settings)


async def notify_prediction_stage(
    chat_id: int,
    user_id: UUID,
    target: date,
    stage: PredictionStage,
    *,
    with_typing: bool = True,
    settings: Settings | None = None,
) -> int | None:
    job_key = prediction_job_key(target)
    text = prediction_stage_text(stage)
    return await advance_progress(
        chat_id,
        user_id,
        job_key,
        text,
        with_typing=with_typing,
        settings=settings,
    )


async def notify_compatibility_stage(
    chat_id: int,
    user_id: UUID,
    report_id: UUID,
    stage: CompatibilityStage,
    *,
    with_typing: bool = True,
    settings: Settings | None = None,
) -> int | None:
    job_key = compatibility_job_key(report_id)
    text = compatibility_stage_text(stage)
    return await advance_progress(
        chat_id,
        user_id,
        job_key,
        text,
        with_typing=with_typing,
        settings=settings,
    )


async def notify_natal_stage(
    chat_id: int,
    user_id: UUID,
    report_id: UUID,
    stage: NatalStage,
    *,
    with_typing: bool = True,
    settings: Settings | None = None,
) -> int | None:
    job_key = natal_job_key(report_id)
    text = natal_stage_text(stage)
    return await advance_progress(
        chat_id,
        user_id,
        job_key,
        text,
        with_typing=with_typing,
        settings=settings,
    )


async def current_progress_message_id(
    user_id: UUID,
    job_key: str,
) -> int | None:
    """Для повторного клика: тот же progress без дубля (PR4)."""
    return await get_progress_message_id(user_id, job_key)
