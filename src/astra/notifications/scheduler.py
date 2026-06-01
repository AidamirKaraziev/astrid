import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from astra.core.config import Settings, get_settings
from astra.db.session import get_session_factory, init_engine
from astra.messaging.publisher import publish_prediction_generate
from astra.services.prediction_pending import (
    clear_prediction_pending,
    try_mark_prediction_pending,
)
from astra.predictions.models import Prediction
from astra.users.models import User

logger = logging.getLogger(__name__)


def _is_notification_due(
    now_utc: datetime,
    user_timezone: str,
    hour: int,
    minute: int,
) -> bool:
    tz = ZoneInfo(user_timezone)
    local = now_utc.astimezone(tz)
    return local.hour == hour and local.minute == minute


async def process_scheduled_notifications(
    session: AsyncSession,
    bot_send_text,
    settings: Settings | None = None,
) -> int:
    """Enqueue daily prediction send tasks at configured local time."""
    cfg = settings or get_settings()
    now_utc = datetime.now(ZoneInfo("UTC"))
    enqueued = 0

    result = await session.execute(
        select(User)
        .where(User.onboarding_completed.is_(True))
        .options(selectinload(User.profile)),
    )
    users = result.scalars().all()

    for user in users:
        if user.profile is None:
            continue
        if not _is_notification_due(
            now_utc,
            user.profile.timezone,
            cfg.notification_hour,
            cfg.notification_minute,
        ):
            continue

        today_local = now_utc.astimezone(ZoneInfo(user.profile.timezone)).date()
        existing = await session.execute(
            select(Prediction).where(
                Prediction.user_id == user.id,
                Prediction.prediction_date == today_local,
                Prediction.sent_at.is_not(None),
            ),
        )
        if existing.scalar_one_or_none():
            continue

        if cfg.rabbitmq_enabled:
            pred_row = await session.execute(
                select(Prediction).where(
                    Prediction.user_id == user.id,
                    Prediction.prediction_date == today_local,
                ),
            )
            prediction = pred_row.scalar_one_or_none()
            if prediction is None:
                if await try_mark_prediction_pending(user.id, today_local):
                    try:
                        await publish_prediction_generate(user.id, today_local, cfg)
                        enqueued += 1
                    except Exception:
                        await clear_prediction_pending(user.id, today_local)
                        raise
            elif prediction.sent_at is None:
                from astra.messaging.publisher import publish_prediction_send

                if await try_mark_prediction_pending(user.id, today_local):
                    try:
                        await publish_prediction_send(user.id, today_local, cfg)
                        enqueued += 1
                    except Exception:
                        await clear_prediction_pending(user.id, today_local)
                        raise
        else:
            from astra.services.prediction_service import (
                format_prediction_for_user,
                get_or_create_today_prediction,
                mark_prediction_sent,
            )

            try:
                prediction = await get_or_create_today_prediction(
                    session,
                    user,
                    user.profile,
                    today=today_local,
                )
                if prediction is None:
                    continue
                message = format_prediction_for_user(prediction, user, user.profile)
                await bot_send_text(user.telegram_id, message)
                await mark_prediction_sent(session, prediction)
                enqueued += 1
            except Exception:
                logger.exception(
                    "Failed to send notification to telegram_id=%s",
                    user.telegram_id,
                )

    return enqueued


async def notification_worker(
    bot_send_text,
    interval_seconds: int = 60,
    settings: Settings | None = None,
) -> None:
    cfg = settings or get_settings()
    init_engine(cfg)
    while True:
        try:
            async with get_session_factory()() as session:
                count = await process_scheduled_notifications(
                    session,
                    bot_send_text,
                    cfg,
                )
                await session.commit()
                if count:
                    logger.info("Enqueued or sent %s scheduled predictions", count)
        except Exception:
            logger.exception("Notification worker iteration failed")
        await asyncio.sleep(interval_seconds)
