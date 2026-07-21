"""Запросы к пулу призов и выигрышам колеса фортуны."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.payments.models import Product
from astra.wheel.enums import SpinType
from astra.wheel.models import WheelPrize, WheelWin


async def list_active_prizes(session: AsyncSession) -> list[WheelPrize]:
    """Активные сектора колеса; выключенный товар выключает и его призы."""
    result = await session.execute(
        select(WheelPrize)
        .join(Product, Product.code == WheelPrize.product_code)
        .where(WheelPrize.is_active.is_(True), Product.is_active.is_(True))
        .order_by(WheelPrize.created_at),
    )
    return list(result.scalars().all())


async def count_user_wins_by_prize(session: AsyncSession, user_id: UUID) -> dict[UUID, int]:
    """Сколько раз каждый сектор выпадал этому пользователю (для tie-break)."""
    result = await session.execute(
        select(WheelWin.prize_id, func.count())
        .where(WheelWin.user_id == user_id, WheelWin.prize_id.is_not(None))
        .group_by(WheelWin.prize_id),
    )
    return {prize_id: count for prize_id, count in result.all()}


async def has_free_win_on(session: AsyncSession, user_id: UUID, won_on: date) -> bool:
    result = await session.execute(
        select(WheelWin.id).where(
            WheelWin.user_id == user_id,
            WheelWin.spin_type == SpinType.FREE,
            WheelWin.won_on == won_on,
        ),
    )
    return result.first() is not None


async def create_win(
    session: AsyncSession,
    *,
    user_id: UUID,
    prize: WheelPrize,
    spin_type: SpinType,
    won_on: date,
    expires_at: datetime | None,
    payment_id: UUID | None = None,
) -> WheelWin:
    win = WheelWin(
        user_id=user_id,
        prize_id=prize.id,
        product_code=prize.product_code,
        discount_percent=prize.discount_percent,
        spin_type=spin_type,
        won_on=won_on,
        expires_at=expires_at,
        payment_id=payment_id,
    )
    session.add(win)
    await session.flush()
    return win


async def get_win(session: AsyncSession, win_id: UUID) -> WheelWin | None:
    return await session.get(WheelWin, win_id)


async def list_available_wins(
    session: AsyncSession,
    user_id: UUID,
    now: datetime,
) -> list[WheelWin]:
    """Неактивированные и не сгоревшие призы пользователя, свежие сверху."""
    result = await session.execute(
        select(WheelWin)
        .where(
            WheelWin.user_id == user_id,
            WheelWin.activated_at.is_(None),
            (WheelWin.expires_at.is_(None)) | (WheelWin.expires_at > now),
        )
        .order_by(WheelWin.created_at.desc()),
    )
    return list(result.scalars().all())


async def get_pending_win_for_reading(
    session: AsyncSession,
    reading_id: UUID,
) -> WheelWin | None:
    """Приз, зарезервированный под черновик расклада, но ещё не активированный."""
    result = await session.execute(
        select(WheelWin).where(
            WheelWin.reading_id == reading_id,
            WheelWin.activated_at.is_(None),
        ),
    )
    return result.scalar_one_or_none()
