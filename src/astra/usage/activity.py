"""Отметка «человек сегодня был в боте» и связанная с ней серия дней.

Зовётся из middleware на каждый входящий апдейт, поэтому дешевизна важнее
красоты: факт «сегодня уже отмечен» лежит в Redis до конца суток, и на второе,
третье и сотое нажатие в базу мы не ходим вовсе.

Активность — это только то, что сделал сам человек. Присланный нами прогноз,
который он не открыл, активностью не делает; а вот кнопка под этим прогнозом —
уже его действие и считается.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from redis.asyncio import Redis
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import Settings, get_settings
from astra.core.observability import get_logger
from astra.usage.models import ActivityDay
from astra.users.local_time import local_today
from astra.users.models import User

log = get_logger(__name__)

# Дашборд считает по московским суткам: цифры на одном экране должны сходиться
# между собой, а не подстраиваться под часовой пояс каждого пользователя.
DASHBOARD_TIMEZONE = ZoneInfo("Europe/Moscow")


def dashboard_today(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(DASHBOARD_TIMEZONE).date()


def _cache_key(user_id, day_msk: date, day_local: date) -> str:
    return f"astra:activity:{user_id}:{day_msk}:{day_local}"


async def mark_active(
    session: AsyncSession,
    user: User,
    *,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> bool:
    """Отметить день активности и продлить серию. True — отметили впервые.

    Идемпотентно по паре «московский день × локальный день»: у человека,
    активного поздно вечером, эти даты расходятся, и обе нужны — первая для
    дашборда, вторая для серии.
    """
    from astra.services.points_service import register_daily_activity

    cfg = settings or get_settings()
    day_msk = dashboard_today(now)
    day_local = local_today(user, now)
    key = _cache_key(user.id, day_msk, day_local)

    client = None
    try:
        client = Redis.from_url(cfg.redis_url, decode_responses=True)
        # NX: ставим отметку только если её ещё нет — так «уже отмечен сегодня»
        # стоит один поход в Redis вместо запроса в базу.
        fresh = await client.set(key, "1", nx=True, ex=_seconds_until_midnight(now))
    except Exception:
        # Redis прилёг — работаем без кеша, база разрулит дубли сама.
        log.warning("activity.cache_unavailable", user_id=str(user.id))
        fresh = True
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001 — закрытие не должно ломать апдейт
                pass

    if not fresh:
        return False

    # Запоминаем до начисления: register_daily_activity перепишет поле, а нам
    # нужно знать, был ли человек в боте раньше сегодняшнего дня.
    came_before = user.last_active_date is not None and user.last_active_date != day_local

    await session.execute(
        insert(ActivityDay)
        .values(user_id=user.id, day_msk=day_msk, day_local=day_local)
        .on_conflict_do_nothing(constraint="uq_activity_days_user_day"),
    )
    await register_daily_activity(session, user, activity_date=day_local)

    if came_before:
        # Новичок вернулся — приглашение состоялось, пригласившему капают звёзды.
        # Ошибка здесь не должна ронять апдейт: награда не важнее ответа боту.
        from astra.services.referral_service import reward_referrer_on_return

        try:
            await reward_referrer_on_return(session, user, settings=cfg)
        except Exception:
            log.warning("referral.reward_on_return_failed", user_id=str(user.id), exc_info=True)
    return True


def _seconds_until_midnight(now: datetime | None = None) -> int:
    """Сколько жить отметке: до московской полуночи, минимум минута."""
    moment = (now or datetime.now(UTC)).astimezone(DASHBOARD_TIMEZONE)
    tomorrow = datetime.combine(
        moment.date() + timedelta(days=1),
        datetime.min.time(),
        tzinfo=DASHBOARD_TIMEZONE,
    )
    return max(60, int((tomorrow - moment).total_seconds()))
