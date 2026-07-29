"""Ряды для дашборда: активность, генерации и выручка по периодам.

Периоды календарные и московские: неделя с понедельника, месяц с первого
числа, сутки — по Москве. Скользящие окна («последние 7 дней») тут намеренно
не используются: их нельзя сравнить с прошлым месяцем и нельзя назвать вслух.

Уникальные люди считаются внутри каждого периода, поэтому месячное число
меньше суммы дневных: человек, заходивший десять дней, в месяце один. Это не
ошибка выгрузки, а свойство метрики — на экране оно подписано.

Текущий период всегда неполный: он идёт прямо сейчас. Помечаем его флагом,
чтобы столбик-огрызок не читался как обвал.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from sqlalchemy import Date, cast, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.payments.enums import PaymentStatus
from astra.payments.models import Payment
from astra.llm.models import LlmCall
from astra.usage.activity import DASHBOARD_TIMEZONE, dashboard_today
from astra.usage.models import ActivityDay, UsageEvent


class Grain(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


# Глубина каждого разреза: месяц по дням, квартал с лишним по неделям, год по месяцам.
DEPTH = {Grain.DAY: 30, Grain.WEEK: 12, Grain.MONTH: 12}

GRAIN_LABELS = {Grain.DAY: "Дни", Grain.WEEK: "Недели", Grain.MONTH: "Месяцы"}


@dataclass(frozen=True, slots=True)
class Bucket:
    """Один столбик: начало периода, подпись и признак незавершённости."""

    start: date
    label: str
    current: bool = False


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _shift_month(day: date, months: int) -> date:
    total = day.year * 12 + (day.month - 1) + months
    return date(total // 12, total % 12 + 1, 1)


def buckets(grain: Grain, today: date | None = None) -> list[Bucket]:
    """Календарные периоды до сегодняшнего дня включительно, старые слева."""
    now = today or dashboard_today()
    depth = DEPTH[grain]

    if grain is Grain.DAY:
        starts = [now - timedelta(days=offset) for offset in range(depth - 1, -1, -1)]
        labels = [start.strftime("%d.%m") for start in starts]
    elif grain is Grain.WEEK:
        first = _week_start(now)
        starts = [first - timedelta(weeks=offset) for offset in range(depth - 1, -1, -1)]
        labels = [start.strftime("%d.%m") for start in starts]
    else:
        first = _month_start(now)
        starts = [_shift_month(first, -offset) for offset in range(depth - 1, -1, -1)]
        months = (
            "янв", "фев", "мар", "апр", "май", "июн",
            "июл", "авг", "сен", "окт", "ноя", "дек",
        )
        labels = [months[start.month - 1] for start in starts]

    return [
        Bucket(start=start, label=label, current=start == starts[-1])
        for start, label in zip(starts, labels, strict=True)
    ]


def _bucket_of(day: date, grain: Grain) -> date:
    if grain is Grain.DAY:
        return day
    if grain is Grain.WEEK:
        return _week_start(day)
    return _month_start(day)


def _range(items: list[Bucket], grain: Grain) -> tuple[date, date]:
    """Границы выборки: от начала первого периода до конца последнего."""
    start = items[0].start
    last = items[-1].start
    if grain is Grain.DAY:
        end = last + timedelta(days=1)
    elif grain is Grain.WEEK:
        end = last + timedelta(weeks=1)
    else:
        end = _shift_month(last, 1)
    return start, end


def _moscow_date(column):
    """Дата столбца-времени в московских сутках — та же нарезка, что у активности.

    Имя пояса подставляем литералом, а не параметром: asyncpg отправляет
    параметр как varchar, и postgres не находит timezone(varchar, timestamptz).
    """
    zone = literal_column(f"'{DASHBOARD_TIMEZONE}'")
    return cast(func.timezone(zone, column), Date)


async def active_people(
    session: AsyncSession,
    grain: Grain,
    items: list[Bucket],
) -> list[int]:
    """Уникальные люди внутри каждого периода (не сумма дневных!)."""
    start, end = _range(items, grain)
    rows = (
        await session.execute(
            select(ActivityDay.day_msk, ActivityDay.user_id).where(
                ActivityDay.day_msk >= start,
                ActivityDay.day_msk < end,
            ),
        )
    ).all()

    seen: dict[date, set] = {item.start: set() for item in items}
    for day, user_id in rows:
        key = _bucket_of(day, grain)
        if key in seen:
            seen[key].add(user_id)
    return [len(seen[item.start]) for item in items]


async def products_given(
    session: AsyncSession,
    grain: Grain,
    items: list[Bucket],
) -> list[int]:
    """Сколько результатов люди получили — польза, а не расход."""
    start, end = _range(items, grain)
    rows = (
        await session.execute(
            select(_moscow_date(UsageEvent.created_at), func.count(UsageEvent.id))
            .where(
                _moscow_date(UsageEvent.created_at) >= start,
                _moscow_date(UsageEvent.created_at) < end,
            )
            .group_by(_moscow_date(UsageEvent.created_at)),
        )
    ).all()
    return _fold(rows, grain, items)


async def llm_calls(
    session: AsyncSession,
    grain: Grain,
    items: list[Bucket],
) -> list[int]:
    """Сколько раз дёрнули модель — у одного отчёта их бывает несколько."""
    start, end = _range(items, grain)
    rows = (
        await session.execute(
            select(_moscow_date(LlmCall.created_at), func.count(LlmCall.id))
            .where(
                _moscow_date(LlmCall.created_at) >= start,
                _moscow_date(LlmCall.created_at) < end,
            )
            .group_by(_moscow_date(LlmCall.created_at)),
        )
    ).all()
    return _fold(rows, grain, items)


async def revenue(
    session: AsyncSession,
    grain: Grain,
    items: list[Bucket],
) -> list[int]:
    start, end = _range(items, grain)
    rows = (
        await session.execute(
            select(_moscow_date(Payment.created_at), func.coalesce(func.sum(Payment.amount), 0))
            .where(
                Payment.status == PaymentStatus.COMPLETED,
                _moscow_date(Payment.created_at) >= start,
                _moscow_date(Payment.created_at) < end,
            )
            .group_by(_moscow_date(Payment.created_at)),
        )
    ).all()
    return _fold(rows, grain, items)


def _fold(rows, grain: Grain, items: list[Bucket]) -> list[int]:
    """Схлопнуть дневные суммы в периоды выбранной крупности."""
    totals: dict[date, int] = {item.start: 0 for item in items}
    for day, value in rows:
        key = _bucket_of(day, grain)
        if key in totals:
            totals[key] += int(value)
    return [totals[item.start] for item in items]


@dataclass(frozen=True, slots=True)
class Timeline:
    """Всё, что рисуется столбиками, одним объектом."""

    grain: Grain
    buckets: list[Bucket]
    people: list[int]
    products: list[int]
    calls: list[int]
    money: list[int]

    @property
    def rows(self):
        return zip(self.buckets, self.people, self.products, self.calls, self.money, strict=True)


async def collect(session: AsyncSession, grain: Grain, today: date | None = None) -> Timeline:
    items = buckets(grain, today)
    return Timeline(
        grain=grain,
        buckets=items,
        people=await active_people(session, grain, items),
        products=await products_given(session, grain, items),
        calls=await llm_calls(session, grain, items),
        money=await revenue(session, grain, items),
    )


@dataclass(frozen=True, slots=True)
class LlmSpend:
    """Расход на модели за период — рядом с графиком генераций."""

    calls: int = 0
    failed: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    unknown_tokens: int = 0

    @property
    def tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


async def llm_spend(session: AsyncSession, since: datetime) -> LlmSpend:
    row = (
        await session.execute(
            select(
                func.count(LlmCall.id),
                func.count(LlmCall.id).filter(LlmCall.status != "ok"),
                func.coalesce(func.sum(LlmCall.prompt_tokens), 0),
                func.coalesce(func.sum(LlmCall.completion_tokens), 0),
                func.coalesce(func.sum(LlmCall.cost_usd), 0),
                func.count(LlmCall.id).filter(LlmCall.prompt_tokens.is_(None)),
            ).where(LlmCall.created_at >= since),
        )
    ).one()
    return LlmSpend(
        calls=int(row[0]),
        failed=int(row[1]),
        prompt_tokens=int(row[2]),
        completion_tokens=int(row[3]),
        cost_usd=float(row[4]),
        unknown_tokens=int(row[5]),
    )


async def spend_by_product(session: AsyncSession, since: datetime) -> list[tuple[str, int, float]]:
    """Во что обходится каждый продукт: назначение, вызовы, доллары."""
    rows = (
        await session.execute(
            select(
                LlmCall.purpose,
                func.count(LlmCall.id),
                func.coalesce(func.sum(LlmCall.cost_usd), 0),
            )
            .where(LlmCall.created_at >= since)
            .group_by(LlmCall.purpose)
            .order_by(func.coalesce(func.sum(LlmCall.cost_usd), 0).desc()),
        )
    ).all()
    return [(purpose, int(calls), float(cost)) for purpose, calls, cost in rows]
