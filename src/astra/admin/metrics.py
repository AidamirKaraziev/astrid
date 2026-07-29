"""Запросы метрик: деньги, воронка, аудитория, продукты, колесо, рефералы.

Здесь только чтение и агрегация — ни одна функция ничего не меняет. Всё
считается запросами к боевым таблицам, отдельного хранилища агрегатов нет:
на нынешних объёмах это дешевле, чем поддерживать витрину.

Договорённости по датам:

* деньги и заказы считаем по `created_at` (UTC) — бухгалтерия живёт в UTC;
* активность людей — по `usage_events.local_date`, то есть по дню человека:
  иначе вечерняя активность пользователя восточнее уезжает в завтра.

Скидки: при 100% инвойс не выставляется вовсе, поэтому бесплатная выдача
платежа не создаёт. Такие случаи видны только в журнале использования — там
у них `is_paid = false`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import case, distinct, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.ask.models import AskReading
from astra.payments.enums import PaymentStatus
from astra.payments.models import Payment, Product
from astra.referrals.models import Referral
from astra.tarot.models import TarotReading
from astra.usage.models import UsageEvent
from astra.users.models import User
from astra.wheel.models import WheelPrize, WheelWin

# Окно по умолчанию: неделя. На нынешних объёмах дневная разбивка слишком
# шумная — две покупки против пяти выглядят как рост в два с половиной раза.
DEFAULT_DAYS = 7

# Границы для разбивки серий (метрика 16): 1..7, затем 14 и 30.
STREAK_BUCKETS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 14, 30)


def _since(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


@dataclass(frozen=True, slots=True)
class Money:
    """Деньги за период (метрики 1, 2, 3, 4)."""

    revenue: int = 0
    payments: int = 0
    buyers: int = 0
    refunds: int = 0
    refunded_amount: int = 0
    discount_given: int = 0

    @property
    def average_check(self) -> int:
        return round(self.revenue / self.payments) if self.payments else 0


@dataclass(frozen=True, slots=True)
class Repeat:
    """Повторные покупки и выручка на платящего (метрики 5, 6)."""

    paying_users: int = 0
    repeat_users: int = 0
    revenue_total: int = 0

    @property
    def repeat_share(self) -> float:
        return round(self.repeat_users * 100 / self.paying_users, 1) if self.paying_users else 0.0

    @property
    def revenue_per_buyer(self) -> int:
        return round(self.revenue_total / self.paying_users) if self.paying_users else 0


@dataclass(frozen=True, slots=True)
class FunnelStep:
    name: str
    people: int

    def share(self, total: int) -> float:
        return round(self.people * 100 / total, 1) if total else 0.0


@dataclass(frozen=True, slots=True)
class ProductUsage:
    """Строка «чем пользуются» (метрика 12 и популярность продуктов)."""

    action: str
    title: str
    uses: int
    users: int
    paid_uses: int

    @property
    def free_uses(self) -> int:
        return self.uses - self.paid_uses


@dataclass(frozen=True, slots=True)
class Audience:
    """Активные люди в трёх окнах (метрика 13) и удержание (14)."""

    dau: int = 0
    wau: int = 0
    mau: int = 0
    retention: dict[int, float] = field(default_factory=dict)

    @property
    def stickiness(self) -> float:
        """DAU/MAU — «привычка или разовое развлечение»."""
        return round(self.dau * 100 / self.mau, 1) if self.mau else 0.0


@dataclass(frozen=True, slots=True)
class Wheel:
    """Колесо: вращения, судьба призов, факт против весов (метрики 20–23)."""

    spins_free: int = 0
    spins_paid: int = 0
    wins_total: int = 0
    wins_activated: int = 0
    wins_expired: int = 0
    revenue_from_prizes: int = 0
    prize_rows: tuple[tuple[str, int, float, float], ...] = ()

    @property
    def spins(self) -> int:
        return self.spins_free + self.spins_paid

    @property
    def activation_share(self) -> float:
        return round(self.wins_activated * 100 / self.wins_total, 1) if self.wins_total else 0.0


@dataclass(frozen=True, slots=True)
class Referrals:
    """Приглашённые против остальных (метрика 24)."""

    invited: int = 0
    invited_buyers: int = 0
    organic: int = 0
    organic_buyers: int = 0

    @property
    def invited_conversion(self) -> float:
        return round(self.invited_buyers * 100 / self.invited, 1) if self.invited else 0.0

    @property
    def organic_conversion(self) -> float:
        return round(self.organic_buyers * 100 / self.organic, 1) if self.organic else 0.0


async def money(session: AsyncSession, days: int = DEFAULT_DAYS) -> Money:
    """Выручка, число оплат, возвраты и сумма отданных скидок."""
    since = _since(days)
    paid = Payment.status == PaymentStatus.COMPLETED
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(case((paid, Payment.amount), else_=0)), 0),
                func.count(case((paid, Payment.id))),
                func.count(distinct(case((paid, Payment.user_id)))),
                func.count(case((Payment.status == PaymentStatus.REFUNDED, Payment.id))),
                func.coalesce(
                    func.sum(case((Payment.status == PaymentStatus.REFUNDED, Payment.amount), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(case((paid, Payment.base_amount - Payment.amount), else_=0)),
                    0,
                ),
            ).where(Payment.created_at >= since),
        )
    ).one()
    return Money(*row)


async def revenue_by_day(session: AsyncSession, days: int = DEFAULT_DAYS) -> list[tuple[date, int]]:
    """Выручка по дням — для столбиков; пустые дни заполняем нулями."""
    since = _since(days)
    rows = (
        await session.execute(
            select(
                func.date(Payment.created_at).label("day"),
                func.coalesce(func.sum(Payment.amount), 0),
            )
            .where(Payment.created_at >= since, Payment.status == PaymentStatus.COMPLETED)
            .group_by("day")
            .order_by("day"),
        )
    ).all()
    got = {row[0]: int(row[1]) for row in rows}
    today = datetime.now(UTC).date()
    return [
        (day, got.get(day, 0))
        for day in (today - timedelta(days=offset) for offset in range(days - 1, -1, -1))
    ]


async def repeat_purchases(session: AsyncSession) -> Repeat:
    """Считается за всё время: за неделю повторных покупок почти не бывает."""
    per_user = (
        select(
            Payment.user_id.label("user_id"),
            func.count(Payment.id).label("cnt"),
            func.sum(Payment.amount).label("total"),
        )
        .where(Payment.status == PaymentStatus.COMPLETED)
        .group_by(Payment.user_id)
        .subquery()
    )
    row = (
        await session.execute(
            select(
                func.count(per_user.c.user_id),
                func.count(case((per_user.c.cnt > 1, per_user.c.user_id))),
                func.coalesce(func.sum(per_user.c.total), 0),
            ),
        )
    ).one()
    return Repeat(*row)


async def days_to_first_purchase(session: AsyncSession) -> float | None:
    """Медиана «сколько дней от регистрации до первой покупки» (метрика 7)."""
    first_payment = (
        select(
            Payment.user_id.label("user_id"),
            func.min(Payment.created_at).label("first_at"),
        )
        .where(Payment.status == PaymentStatus.COMPLETED)
        .group_by(Payment.user_id)
        .subquery()
    )
    value = (
        await session.execute(
            select(
                func.percentile_cont(0.5).within_group(
                    func.extract("epoch", first_payment.c.first_at - User.created_at) / 86400,
                ),
            )
            .select_from(first_payment)
            .join(User, User.id == first_payment.c.user_id),
        )
    ).scalar()
    return round(float(value), 1) if value is not None else None


async def funnel(session: AsyncSession) -> list[FunnelStep]:
    """Старт → онбординг → дошёл до оплаты → заплатил → купил второй раз.

    «Дошёл до оплаты» — это созданный черновик разбора: он появляется в базе
    перед выставлением инвойса и остаётся, даже если человек передумал.
    """
    started = (await session.execute(select(func.count(User.id)))).scalar_one()
    onboarded = (
        await session.execute(
            select(func.count(User.id)).where(User.onboarding_completed.is_(True)),
        )
    ).scalar_one()

    tarot_drafts = select(TarotReading.user_id).distinct()
    ask_drafts = select(AskReading.user_id).distinct()
    reached = (
        await session.execute(
            select(func.count(distinct(User.id))).where(
                User.id.in_(tarot_drafts.union(ask_drafts).subquery().select()),
            ),
        )
    ).scalar_one()

    repeat = await repeat_purchases(session)
    return [
        FunnelStep("Запустили бота", started),
        FunnelStep("Прошли онбординг", onboarded),
        FunnelStep("Дошли до оплаты", reached),
        FunnelStep("Оплатили", repeat.paying_users),
        FunnelStep("Купили второй раз", repeat.repeat_users),
    ]


async def product_usage(
    session: AsyncSession,
    days: int = DEFAULT_DAYS,
) -> list[ProductUsage]:
    """Чем пользуются чаще: и платным, и бесплатным (главный вопрос заказчика)."""
    since = _since(days)
    rows = (
        await session.execute(
            select(
                UsageEvent.action,
                func.count(UsageEvent.id),
                func.count(distinct(UsageEvent.user_id)),
                func.coalesce(func.sum(case((UsageEvent.is_paid.is_(True), 1), else_=0)), 0),
            )
            .where(UsageEvent.created_at >= since)
            .group_by(UsageEvent.action)
            .order_by(func.count(UsageEvent.id).desc()),
        )
    ).all()

    titles = dict(
        (await session.execute(select(Product.code, Product.title))).all(),
    )
    known = {
        "day_card": "Карта дня",
        "tarot_daily": "Ежедневное таро",
        "natal_report": "Разбор натальной карты",
        "compatibility": "Совместимость",
    }
    return [
        ProductUsage(
            action=action,
            title=titles.get(action) or known.get(action, action),
            uses=int(uses),
            users=int(users),
            paid_uses=int(paid),
        )
        for action, uses, users, paid in rows
    ]


async def audience(session: AsyncSession) -> Audience:
    """DAU/WAU/MAU и удержание по когортам регистрации."""
    today = datetime.now(UTC).date()

    async def active_since(days: int) -> int:
        return (
            await session.execute(
                select(func.count(distinct(UsageEvent.user_id))).where(
                    UsageEvent.local_date > today - timedelta(days=days),
                ),
            )
        ).scalar_one()

    retention: dict[int, float] = {}
    for day in (1, 7, 30):
        # Когорта: зарегистрировались ровно `day` дней назад (и раньше, если
        # окно шире), вернулись ли хотя бы раз после дня регистрации.
        cohort_start = today - timedelta(days=day + 7)
        cohort_end = today - timedelta(days=day)
        cohort = (
            select(User.id.label("user_id"), func.date(User.created_at).label("joined"))
            .where(
                func.date(User.created_at) >= cohort_start,
                func.date(User.created_at) < cohort_end,
            )
            .subquery()
        )
        size = (await session.execute(select(func.count(cohort.c.user_id)))).scalar_one()
        if not size:
            retention[day] = 0.0
            continue
        returned = (
            await session.execute(
                select(func.count(distinct(UsageEvent.user_id)))
                .select_from(cohort)
                .join(UsageEvent, UsageEvent.user_id == cohort.c.user_id)
                .where(UsageEvent.local_date >= cohort.c.joined + day),
            )
        ).scalar_one()
        retention[day] = round(returned * 100 / size, 1)

    return Audience(
        dau=await active_since(1),
        wau=await active_since(7),
        mau=await active_since(30),
        retention=retention,
    )


async def streak_buckets(session: AsyncSession) -> list[tuple[str, int]]:
    """Распределение серий по группам 1..7, 14, 30 (метрика 16)."""
    rows = (
        await session.execute(
            select(User.streak_current, func.count(User.id))
            .where(User.streak_current > 0)
            .group_by(User.streak_current),
        )
    ).all()
    counts = {int(streak): int(people) for streak, people in rows}

    buckets: list[tuple[str, int]] = []
    for index, low in enumerate(STREAK_BUCKETS):
        high = STREAK_BUCKETS[index + 1] if index + 1 < len(STREAK_BUCKETS) else None
        if high is None:
            label, people = f"{low}+", sum(v for k, v in counts.items() if k >= low)
        elif high == low + 1:
            label, people = str(low), counts.get(low, 0)
        else:
            label = f"{low}–{high - 1}"
            people = sum(v for k, v in counts.items() if low <= k < high)
        buckets.append((label, people))
    return buckets


async def wheel(session: AsyncSession, days: int = DEFAULT_DAYS) -> Wheel:
    """Вращения, судьба призов и фактическое распределение против весов."""
    since = _since(days)
    spins = (
        await session.execute(
            select(WheelWin.spin_type, func.count(WheelWin.id))
            .where(WheelWin.created_at >= since)
            .group_by(WheelWin.spin_type),
        )
    ).all()
    by_type = {str(kind): int(count) for kind, count in spins}

    now = datetime.now(UTC)
    totals = (
        await session.execute(
            select(
                func.count(WheelWin.id),
                func.count(case((WheelWin.activated_at.isnot(None), WheelWin.id))),
                func.count(
                    case(
                        (
                            (WheelWin.activated_at.is_(None)) & (WheelWin.expires_at < now),
                            WheelWin.id,
                        ),
                    ),
                ),
            ).where(WheelWin.created_at >= since),
        )
    ).one()

    revenue = (
        await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .join(WheelWin, WheelWin.reading_id == Payment.reading_id)
            .where(Payment.status == PaymentStatus.COMPLETED, Payment.created_at >= since),
        )
    ).scalar_one()

    # Факт против весов: доля выпадений каждого сектора и его заявленный шанс.
    prizes = (await session.execute(select(WheelPrize).where(WheelPrize.is_active.is_(True)))).scalars().all()
    weight_total = sum(prize.weight for prize in prizes) or 1
    hits = dict(
        (
            await session.execute(
                select(WheelWin.prize_id, func.count(WheelWin.id))
                .where(WheelWin.created_at >= since)
                .group_by(WheelWin.prize_id),
            )
        ).all(),
    )
    spins_total = sum(int(v) for v in hits.values()) or 1
    prize_rows = tuple(
        (
            f"{prize.product_code} −{prize.discount_percent}%",
            int(hits.get(prize.id, 0)),
            round(int(hits.get(prize.id, 0)) * 100 / spins_total, 1),
            round(prize.weight * 100 / weight_total, 1),
        )
        for prize in prizes
    )

    return Wheel(
        spins_free=by_type.get("free", 0),
        spins_paid=by_type.get("paid", 0),
        wins_total=int(totals[0]),
        wins_activated=int(totals[1]),
        wins_expired=int(totals[2]),
        revenue_from_prizes=int(revenue),
        prize_rows=prize_rows,
    )


async def referrals(session: AsyncSession) -> Referrals:
    """Приглашённые покупают чаще или нет (метрика 24)."""
    invited_ids = select(Referral.invitee_id).distinct().subquery().select()
    buyers = (
        select(Payment.user_id)
        .where(Payment.status == PaymentStatus.COMPLETED)
        .distinct()
        .subquery()
        .select()
    )
    row = (
        await session.execute(
            select(
                func.count(case((User.id.in_(invited_ids), User.id))),
                func.count(case(((User.id.in_(invited_ids)) & (User.id.in_(buyers)), User.id))),
                func.count(case((~User.id.in_(invited_ids), User.id))),
                func.count(case(((~User.id.in_(invited_ids)) & (User.id.in_(buyers)), User.id))),
            ),
        )
    ).one()
    return Referrals(*(int(value) for value in row))


async def signups_by_day(session: AsyncSession, days: int = DEFAULT_DAYS) -> int:
    """Сколько людей пришло за период (метрика 8)."""
    return (
        await session.execute(
            select(func.count(User.id)).where(User.created_at >= _since(days)),
        )
    ).scalar_one()


async def failed_share(session: AsyncSession, days: int = DEFAULT_DAYS) -> tuple[int, int]:
    """Сколько разборов упало и сколько всего — за период."""
    since = _since(days)
    failed = 0
    total = 0
    for model in (TarotReading, AskReading):
        row = (
            await session.execute(
                select(
                    func.count(model.id),
                    func.count(case((model.status == "failed", model.id))),
                ).where(model.created_at >= since),
            )
        ).one()
        total += int(row[0])
        failed += int(row[1])
    return failed, total


@dataclass(frozen=True, slots=True)
class Dashboard:
    """Всё, что показывает страница метрик, одним объектом."""

    days: int
    money: Money
    previous: Money
    revenue_days: list[tuple[date, int]]
    funnel: list[FunnelStep]
    products: list[ProductUsage]
    audience: Audience
    streaks: list[tuple[str, int]]
    wheel: Wheel
    referrals: Referrals
    repeat: Repeat
    signups: int
    failed: tuple[int, int]
    days_to_purchase: float | None


async def collect(session: AsyncSession, days: int = DEFAULT_DAYS) -> Dashboard:
    """Один вызов на всю страницу — запросы идут последовательно, их немного."""
    current = await money(session, days)
    previous = Money(
        *(
            await session.execute(
                select(
                    func.coalesce(func.sum(Payment.amount), 0),
                    func.count(Payment.id),
                    func.count(distinct(Payment.user_id)),
                    literal(0),  # возвраты в сравнении периодов не нужны
                    literal(0),
                    func.coalesce(func.sum(Payment.base_amount - Payment.amount), 0),
                ).where(
                    Payment.status == PaymentStatus.COMPLETED,
                    Payment.created_at >= _since(days * 2),
                    Payment.created_at < _since(days),
                ),
            )
        ).one(),
    )
    return Dashboard(
        days=days,
        money=current,
        previous=previous,
        revenue_days=await revenue_by_day(session, days),
        funnel=await funnel(session),
        products=await product_usage(session, days),
        audience=await audience(session),
        streaks=await streak_buckets(session),
        wheel=await wheel(session, days),
        referrals=await referrals(session),
        repeat=await repeat_purchases(session),
        signups=await signups_by_day(session, days),
        failed=await failed_share(session, days),
        days_to_purchase=await days_to_first_purchase(session),
    )
