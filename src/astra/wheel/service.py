"""Логика колеса фортуны: выбор приза, вращение, жизненный цикл выигрыша.

Приз определяется на сервере ДО анимации: взвешенный рандом по weight,
а среди секторов с одинаковым весом побеждает тот, что выпадал этому
пользователю реже всего.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo

from astra.core.observability import Event, get_logger
from astra.users.models import User
from astra.wheel import crud as wheel_crud
from astra.wheel.enums import SpinType
from astra.wheel.models import WheelPrize, WheelWin

log = get_logger(__name__)


def user_local_today(user: User) -> date:
    return datetime.now(ZoneInfo(user.profile.timezone)).date()


def free_win_expiry(user: User, won_on: date) -> datetime:
    """Конец локального дня пользователя (полночь следующего дня) в UTC."""
    tz = ZoneInfo(user.profile.timezone)
    local_midnight = datetime.combine(won_on + timedelta(days=1), time.min, tzinfo=tz)
    return local_midnight.astimezone(UTC)


def choose_prize(
    prizes: Sequence[WheelPrize],
    user_counts: Mapping[UUID, int],
    rng: random.Random | None = None,
) -> WheelPrize:
    """Взвешенный выбор сектора; при равных весах — реже всего выпадавший."""
    if not prizes:
        raise ValueError("пул призов пуст")
    rng = rng or random.Random()
    picked = rng.choices(list(prizes), weights=[p.weight for p in prizes], k=1)[0]
    same_weight = [p for p in prizes if p.weight == picked.weight]
    if len(same_weight) == 1:
        return picked
    min_count = min(user_counts.get(p.id, 0) for p in same_weight)
    rarest = [p for p in same_weight if user_counts.get(p.id, 0) == min_count]
    return picked if picked in rarest else rng.choice(rarest)


async def perform_spin(
    session: AsyncSession,
    user: User,
    spin_type: SpinType,
    *,
    payment_id: UUID | None = None,
    rng: random.Random | None = None,
) -> WheelWin | None:
    """Крутануть колесо и записать выигрыш; None — пул призов пуст."""
    prizes = await wheel_crud.list_active_prizes(session)
    if not prizes:
        log.warning(Event.WHEEL_POOL_EMPTY, user_id=user.id, spin_type=str(spin_type))
        return None
    counts = await wheel_crud.count_user_wins_by_prize(session, user.id)
    prize = choose_prize(prizes, counts, rng)
    won_on = user_local_today(user)
    expires_at = free_win_expiry(user, won_on) if spin_type == SpinType.FREE else None
    win = await wheel_crud.create_win(
        session,
        user_id=user.id,
        prize=prize,
        spin_type=spin_type,
        won_on=won_on,
        expires_at=expires_at,
        payment_id=payment_id,
    )
    log.info(
        Event.WHEEL_SPIN,
        user_id=user.id,
        win_id=win.id,
        prize_id=prize.id,
        product_code=prize.product_code,
        discount_percent=prize.discount_percent,
        spin_type=str(spin_type),
    )
    return win


def win_is_available(win: WheelWin, now: datetime | None = None) -> bool:
    """Приз ещё можно активировать: не использован и не сгорел."""
    if win.activated_at is not None:
        return False
    if win.expires_at is None:
        return True
    return win.expires_at > (now or datetime.now(UTC))


async def reserve_win_for_reading(
    session: AsyncSession,
    win: WheelWin,
    reading_id: UUID,
) -> None:
    """Привязать приз к черновику расклада (до оплаты приз ещё не потрачен)."""
    win.reading_id = reading_id
    await session.flush()


async def mark_win_activated(session: AsyncSession, win: WheelWin) -> None:
    win.activated_at = datetime.now(UTC)
    await session.flush()
    log.info(
        Event.WHEEL_PRIZE_ACTIVATED,
        user_id=win.user_id,
        win_id=win.id,
        product_code=win.product_code,
        discount_percent=win.discount_percent,
    )
