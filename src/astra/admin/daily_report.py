"""Ежедневная сводка: как продвигается продукт, одним сообщением.

Здесь только текст — отправку делает планировщик в `astra.notifications`.
Так панель остаётся без зависимости от aiogram и переезжает в отдельный
сервис без переделок.

Формат подобран под чтение с телефона: сначала вчерашние деньги и люди,
потом что покупали и чем пользовались, в конце — что сломалось. Числа даём
со сравнением: «43 ⭐» само по себе ничего не говорит, «43 ⭐ (+18%)» — уже да.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.admin import metrics
from astra.payments.enums import PaymentStatus
from astra.payments.models import Payment
from astra.usage.models import UsageEvent
from astra.users.models import User

_TOP_PRODUCTS = 5


def _stars(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " ⭐"


def _times(count: int) -> str:
    """«1 раз», «2 раза», «5 раз» — сводку читают люди, а не парсер."""
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} раз"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} раза"
    return f"{count} раз"


def _change(current: int, previous: int) -> str:
    if not previous:
        return "" if not current else " (первые)"
    delta = round((current - previous) * 100 / previous)
    if delta == 0:
        return " (как вчера)"
    return f" ({'+' if delta > 0 else ''}{delta}%)"


async def _day_money(session: AsyncSession, day: date) -> tuple[int, int, int]:
    """Выручка, оплаты и платящие за конкретные календарные сутки (UTC)."""
    start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(Payment.amount), 0),
                func.count(Payment.id),
                func.count(distinct(Payment.user_id)),
            ).where(
                Payment.status == PaymentStatus.COMPLETED,
                Payment.created_at >= start,
                Payment.created_at < start + timedelta(days=1),
            ),
        )
    ).one()
    return int(row[0]), int(row[1]), int(row[2])


async def _day_usage(session: AsyncSession, day: date) -> list[tuple[str, int, int]]:
    """Что использовали за день: действие, сколько раз, сколько людей."""
    rows = (
        await session.execute(
            select(
                UsageEvent.action,
                func.count(UsageEvent.id),
                func.count(distinct(UsageEvent.user_id)),
                func.coalesce(func.sum(case((UsageEvent.is_paid.is_(True), 1), else_=0)), 0),
            )
            .where(UsageEvent.local_date == day)
            .group_by(UsageEvent.action)
            .order_by(func.count(UsageEvent.id).desc()),
        )
    ).all()
    return [(action, int(uses), int(users)) for action, uses, users, _ in rows]


async def _day_signups(session: AsyncSession, day: date) -> int:
    start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
    return (
        await session.execute(
            select(func.count(User.id)).where(
                User.created_at >= start,
                User.created_at < start + timedelta(days=1),
            ),
        )
    ).scalar_one()


async def build_daily_report(session: AsyncSession, day: date | None = None) -> str:
    """Текст сводки за день (по умолчанию — за вчера), HTML для Telegram."""
    target = day or (datetime.now(UTC).date() - timedelta(days=1))
    before = target - timedelta(days=1)

    revenue, payments, buyers = await _day_money(session, target)
    prev_revenue, prev_payments, _ = await _day_money(session, before)
    signups = await _day_signups(session, target)
    prev_signups = await _day_signups(session, before)
    usage = await _day_usage(session, target)
    audience = await metrics.audience(session)
    failed, total = await metrics.failed_share(session, days=1)

    titles = {
        product.action: product.title
        for product in await metrics.product_usage(session, days=1)
    }

    lines = [
        f"<b>Astra за {target.strftime('%d.%m')}</b>",
        "",
        f"💜 Выручка: <b>{_stars(revenue)}</b>{_change(revenue, prev_revenue)}",
        f"✨ Оплат: <b>{payments}</b>{_change(payments, prev_payments)} · платили {buyers} чел.",
        f"🔮 Новых людей: <b>{signups}</b>{_change(signups, prev_signups)}",
        f"💫 Активных: {audience.dau} за день · {audience.wau} за неделю "
        f"· липкость {audience.stickiness}%",
    ]

    if usage:
        lines += ["", "<b>Чем пользовались</b>"]
        for action, uses, users in usage[:_TOP_PRODUCTS]:
            title = titles.get(action, action)
            lines.append(f"· {title} — {_times(uses)}, {users} чел.")
        if len(usage) > _TOP_PRODUCTS:
            lines.append(f"· и ещё {len(usage) - _TOP_PRODUCTS} продуктов")
    else:
        lines += ["", "Продуктами вчера не пользовались."]

    if failed:
        lines += ["", f"⚠️ Упало разборов: <b>{failed}</b> из {total} — загляни в очередь"]

    return "\n".join(lines)
