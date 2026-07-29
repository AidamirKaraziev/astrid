"""Запись использования продукта и связанная с ней серия дней.

Одна точка входа — `record_usage`. Её зовут там, где продукт уже отдан
человеку, и она делает две вещи: кладёт строку в журнал и двигает серию.
Раньше серию двигал только обработчик `/start`, поэтому у человека, который
заходил в бота из списка чатов и жал кнопки, серия навсегда оставалась
единицей.

Журнал пишется в транзакции самого действия: если действие откатится,
использование не засчитается.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.observability import get_logger
from astra.usage.enums import UsageKind
from astra.usage.models import UsageEvent
from astra.users.local_time import local_today
from astra.users.models import User

log = get_logger(__name__)


async def record_usage(
    session: AsyncSession,
    user: User,
    *,
    action: str,
    kind: UsageKind,
    is_paid: bool = False,
    on_date: date | None = None,
) -> UsageEvent:
    """Записать использование продукта и продлить серию дней.

    `action` у платных продуктов совпадает с `product_code` каталога — так
    метрики использования и выручки сходятся по одному ключу.
    """
    from astra.services.points_service import register_daily_activity

    day = on_date or local_today(user)
    event = UsageEvent(
        user_id=user.id,
        action=action,
        kind=str(kind),
        is_paid=is_paid,
        local_date=day,
    )
    session.add(event)
    await session.flush()

    await register_daily_activity(session, user, activity_date=day)
    log.info("usage.recorded", user_id=user.id, action=action, kind=str(kind), is_paid=is_paid)
    return event
