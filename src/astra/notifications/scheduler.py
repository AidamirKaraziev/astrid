import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger
from astra.services.prediction_pending import (
    clear_prediction_pending,
    try_mark_prediction_pending,
)
from astra.services.prediction_pipeline import (
    enqueue_prediction_pipeline,
    resume_prediction_pipeline,
)
from astra.predictions.models import Prediction
from astra.users.models import User

log = get_logger(__name__)


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
    """Enqueue daily prediction tasks at configured local time (без staged UX)."""
    del bot_send_text
    cfg = settings or get_settings()
    now_utc = datetime.now(ZoneInfo("UTC"))
    enqueued = 0

    result = await session.execute(
        select(User)
        .where(User.onboarding_completed.is_(True))
        .where(User.bot_blocked_at.is_(None))  # заблокировавшие бота — вне рассылки
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

        pred_row = await session.execute(
            select(Prediction).where(
                Prediction.user_id == user.id,
                Prediction.prediction_date == today_local,
            ),
        )
        prediction = pred_row.scalar_one_or_none()

        if not await try_mark_prediction_pending(user.id, today_local):
            continue

        try:
            if prediction is None:
                await enqueue_prediction_pipeline(session, user.id, today_local)
            else:
                await resume_prediction_pipeline(
                    session,
                    user.id,
                    today_local,
                    prediction,
                )
            enqueued += 1
        except Exception:
            await clear_prediction_pending(user.id, today_local)
            raise

    return enqueued


async def send_daily_report_if_due(
    session: AsyncSession,
    bot_send_text,
    settings: Settings | None = None,
    now_utc: datetime | None = None,
) -> bool:
    """Раз в сутки отправить сводку в группу операторов. True — отправили.

    Сводка уходит в тот же час, что задан в конфиге, и ровно один раз: отметка
    о последней отправке живёт в памяти процесса, а совпадение по минуте не даёт
    повторов внутри часа.
    """
    cfg = settings or get_settings()
    if not cfg.admin_report_enabled or not cfg.telegram_admin_group_id:
        return False

    now = (now_utc or datetime.now(ZoneInfo("UTC"))).astimezone(
        ZoneInfo(cfg.admin_report_timezone),
    )
    if now.hour != cfg.admin_report_hour or now.minute != 0:
        return False
    if _last_report_sent.get("day") == now.date():
        return False

    from astra.admin.daily_report import build_daily_report

    text = await build_daily_report(session)
    await bot_send_text(cfg.telegram_admin_group_id, text)
    _last_report_sent["day"] = now.date()
    log.info("admin.daily_report.sent", chat_id=cfg.telegram_admin_group_id)
    return True


# Последний день, за который сводка уже ушла (в памяти процесса).
_last_report_sent: dict[str, object] = {}


async def notification_worker(
    bot_send_text,
    interval_seconds: int = 60,
    settings: Settings | None = None,
) -> None:
    cfg = settings or get_settings()
    from astra.db.session import get_session_factory, init_engine

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
                    log.info(Event.SCHEDULER_ENQUEUED, count=count)
        except Exception:
            log.exception(Event.SCHEDULER_ITERATION_FAILED)

        # Сводка отдельно от прогнозов: её падение не должно рвать рассылку.
        try:
            async with get_session_factory()() as session:
                await send_daily_report_if_due(session, bot_send_text, cfg)
        except Exception:
            log.exception("admin.daily_report.failed")

        await asyncio.sleep(interval_seconds)
