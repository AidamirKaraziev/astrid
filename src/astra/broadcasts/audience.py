"""Сбор аудитории рассылки по фильтрам.

Условия складываются: выбрал три — попадают те, у кого верны все три. Отдельно
есть исключения: «Овны, которые покупали, но не заходили неделю» собирается как
включение по знаку и покупкам минус те, кто был активен за неделю.

Заблокировавшие бота выкидываются всегда и не считаются: слать им бессмысленно,
а в статистике они создают видимость охвата, которого нет.

Каждый фильтр — это подзапрос по id пользователей. Так их можно свободно
комбинировать пересечением и вычитанием, не собирая монструозный JOIN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, distinct, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.ask.enums import AskStatus
from astra.ask.models import AskReading
from astra.payments.enums import PaymentStatus
from astra.payments.models import Payment
from astra.tarot.enums import ReadingStatus
from astra.tarot.models import TarotReading
from astra.usage.models import ActivityDay, UsageEvent
from astra.users.models import Profile, User
from astra.wheel.models import WheelWin

# Знаки зодиака: (название, месяц и день начала). Козерог переходит через год,
# поэтому он и первый, и последний в списке границ.
ZODIAC = (
    ("Козерог", (12, 22)),
    ("Водолей", (1, 20)),
    ("Рыбы", (2, 19)),
    ("Овен", (3, 21)),
    ("Телец", (4, 20)),
    ("Близнецы", (5, 21)),
    ("Рак", (6, 21)),
    ("Лев", (7, 23)),
    ("Дева", (8, 23)),
    ("Весы", (9, 23)),
    ("Скорпион", (10, 23)),
    ("Стрелец", (11, 22)),
)

ZODIAC_NAMES = tuple(name for name, _ in ZODIAC)


def zodiac_bounds(sign: str) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """Границы знака: (месяц, день) начала и конца включительно."""
    names = [name for name, _ in ZODIAC]
    if sign not in names:
        return None
    index = names.index(sign)
    start = ZODIAC[index][1]
    following = ZODIAC[(index + 1) % len(ZODIAC)][1]
    month, day = following
    end = (month, day - 1) if day > 1 else (month - 1 or 12, 31)
    return start, end


@dataclass(slots=True)
class Criteria:
    """Условия отбора. Пустое поле — фильтр не участвует."""

    # Кто человек
    zodiac: set[str] = field(default_factory=set)
    gender: str = ""
    # Как давно с нами
    joined_within_days: int | None = None
    joined_before_days: int | None = None
    onboarding: str = ""  # done | pending
    # Как пользуется
    active_within_days: int | None = None
    sleeping_since_days: int | None = None
    used_products: set[str] = field(default_factory=set)
    # Деньги
    money: str = ""  # paid | never
    spent_at_least: int | None = None
    # Незакрытые хвосты
    abandoned_draft: bool = False
    unclaimed_prize: bool = False
    # Исключения — те же по смыслу, но вычитаются
    exclude_active_within_days: int | None = None
    exclude_paid: bool = False
    exclude_used_products: set[str] = field(default_factory=set)

    def is_empty(self) -> bool:
        return not any(
            [
                self.zodiac,
                self.gender,
                self.joined_within_days,
                self.joined_before_days,
                self.onboarding,
                self.active_within_days,
                self.sleeping_since_days,
                self.used_products,
                self.money,
                self.spent_at_least,
                self.abandoned_draft,
                self.unclaimed_prize,
            ],
        )


def _since(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def _zodiac_condition(signs: set[str]):
    """Условие «день рождения попадает в знак» по месяцу и числу."""
    month = extract("month", Profile.birth_date)
    day = extract("day", Profile.birth_date)
    parts = []
    for sign in signs:
        bounds = zodiac_bounds(sign)
        if bounds is None:
            continue
        (start_month, start_day), (end_month, end_day) = bounds
        after_start = or_(month > start_month, (month == start_month) & (day >= start_day))
        before_end = or_(month < end_month, (month == end_month) & (day <= end_day))
        # Козерог переваливает через новый год: у него границы «или-или».
        parts.append(or_(after_start, before_end) if start_month > end_month else (after_start & before_end))
    return or_(*parts) if parts else None


def _include_queries(criteria: Criteria) -> list[Select]:
    """Каждый включающий фильтр — отдельная выборка id; итог их пересечение."""
    queries: list[Select] = []

    if criteria.zodiac:
        condition = _zodiac_condition(criteria.zodiac)
        if condition is not None:
            queries.append(select(Profile.user_id).where(condition))

    if criteria.gender:
        queries.append(select(Profile.user_id).where(Profile.gender == criteria.gender))

    if criteria.joined_within_days:
        queries.append(select(User.id).where(User.created_at >= _since(criteria.joined_within_days)))

    if criteria.joined_before_days:
        queries.append(select(User.id).where(User.created_at < _since(criteria.joined_before_days)))

    if criteria.onboarding == "done":
        queries.append(select(User.id).where(User.onboarding_completed.is_(True)))
    elif criteria.onboarding == "pending":
        queries.append(select(User.id).where(User.onboarding_completed.is_(False)))

    if criteria.active_within_days:
        queries.append(
            select(distinct(ActivityDay.user_id)).where(
                ActivityDay.day_msk >= _since(criteria.active_within_days).date(),
            ),
        )

    if criteria.sleeping_since_days:
        # Спящие: те, кого нет среди активных за период.
        recent = select(distinct(ActivityDay.user_id)).where(
            ActivityDay.day_msk >= _since(criteria.sleeping_since_days).date(),
        )
        queries.append(select(User.id).where(User.id.notin_(recent)))

    if criteria.used_products:
        queries.append(
            select(distinct(UsageEvent.user_id)).where(
                UsageEvent.action.in_(criteria.used_products),
            ),
        )

    paid_users = select(distinct(Payment.user_id)).where(
        Payment.status == PaymentStatus.COMPLETED,
    )
    if criteria.money == "paid":
        queries.append(paid_users)
    elif criteria.money == "never":
        queries.append(select(User.id).where(User.id.notin_(paid_users)))

    if criteria.spent_at_least:
        queries.append(
            select(Payment.user_id)
            .where(Payment.status == PaymentStatus.COMPLETED)
            .group_by(Payment.user_id)
            .having(func.sum(Payment.amount) >= criteria.spent_at_least),
        )

    if criteria.abandoned_draft:
        tarot = select(distinct(TarotReading.user_id)).where(
            TarotReading.status == ReadingStatus.PENDING_PAYMENT,
        )
        ask = select(distinct(AskReading.user_id)).where(
            AskReading.status == AskStatus.PENDING_PAYMENT,
        )
        queries.append(select(User.id).where(or_(User.id.in_(tarot), User.id.in_(ask))))

    if criteria.unclaimed_prize:
        now = datetime.now(UTC)
        queries.append(
            select(distinct(WheelWin.user_id)).where(
                WheelWin.activated_at.is_(None),
                or_(WheelWin.expires_at.is_(None), WheelWin.expires_at > now),
            ),
        )

    return queries


def _exclude_queries(criteria: Criteria) -> list[Select]:
    queries: list[Select] = []
    if criteria.exclude_active_within_days:
        queries.append(
            select(distinct(ActivityDay.user_id)).where(
                ActivityDay.day_msk >= _since(criteria.exclude_active_within_days).date(),
            ),
        )
    if criteria.exclude_paid:
        queries.append(
            select(distinct(Payment.user_id)).where(Payment.status == PaymentStatus.COMPLETED),
        )
    if criteria.exclude_used_products:
        queries.append(
            select(distinct(UsageEvent.user_id)).where(
                UsageEvent.action.in_(criteria.exclude_used_products),
            ),
        )
    return queries


def build_query(criteria: Criteria) -> Select:
    """Итоговая выборка людей: пересечение включений минус исключения."""
    query = select(User).where(User.bot_blocked_at.is_(None))

    for include in _include_queries(criteria):
        query = query.where(User.id.in_(include))
    for exclude in _exclude_queries(criteria):
        query = query.where(User.id.notin_(exclude))

    return query.order_by(User.created_at)


async def resolve(session: AsyncSession, criteria: Criteria) -> list[User]:
    """Люди, попавшие под фильтры. Заблокировавшие бота отсеяны."""
    rows = await session.execute(build_query(criteria))
    return list(rows.scalars().all())


async def count(session: AsyncSession, criteria: Criteria) -> int:
    """Размер аудитории — показываем до отправки, чтобы не слать вслепую."""
    inner = build_query(criteria).subquery()
    return (await session.execute(select(func.count()).select_from(inner))).scalar_one()
