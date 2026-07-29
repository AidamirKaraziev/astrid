"""Лента событий: всё, что происходило с деньгами и заказами.

Собирается не из одной таблицы, а из шести: платежи, четыре вида заказов и
вращения колеса. Причина простая — «бесплатной транзакции» в базе нет. Когда
скидка 100%, инвойс не выставляется вовсе, и платёж не создаётся: бесплатная
выдача видна только в самом заказе.

Платный заказ даёт две строки: «оплата» в момент списания и «выдача» в момент,
когда человек получил результат. Так сразу видно случаи, где деньги ушли, а
выдачи не случилось, — их не заметить, если склеить всё в одну строку.

Незавершённое тоже здесь: брошенные черновики, упавшие и зависшие заказы.
Поэтому лента строится из заказов, а не из журнала использования — тот пишется
только при успехе и о неудачах ничего не знает.

Страницы по 50. Каждый источник отдаёт свои строки за период, они сливаются в
памяти и режутся на страницы: при нынешних объёмах это дешевле и понятнее, чем
UNION на шесть таблиц с сортировкой в базе.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.ask.enums import AskStatus
from astra.ask.models import AskReading
from astra.compatibility.enums import ReportStatus
from astra.compatibility.models import CompatibilityReport
from astra.natal_report.enums import NatalReportStatus
from astra.natal_report.models import NatalReport
from astra.payments.enums import PaymentStatus
from astra.payments.models import Payment, Product
from astra.tarot.enums import ReadingStatus
from astra.tarot.models import TarotReading
from astra.usage.enums import ACTION_DAY_CARD, ACTION_TAROT_DAILY
from astra.usage.models import UsageEvent
from astra.users.models import User
from astra.wheel.models import WheelWin

PAGE_SIZE = 50

# Товары без строки в каталоге: бесплатные продукты и ежедневные механики.
EXTRA_PRODUCTS = {
    ACTION_DAY_CARD: "Карта дня",
    ACTION_TAROT_DAILY: "Ежедневное таро",
    "natal_report": "Разбор натальной карты",
    "compatibility": "Совместимость",
}


class Kind(StrEnum):
    PAYMENT = "payment"
    REFUND = "refund"
    DELIVERY = "delivery"
    DRAFT = "draft"
    TROUBLE = "trouble"
    SPIN = "spin"


KIND_LABELS = {
    Kind.PAYMENT: "Оплаты",
    Kind.REFUND: "Возвраты",
    Kind.DELIVERY: "Выдачи",
    Kind.DRAFT: "Черновики",
    Kind.TROUBLE: "Аварии",
    Kind.SPIN: "Колесо",
}

PERIODS = {
    "today": "Сегодня",
    "7": "7 дней",
    "30": "30 дней",
    "all": "Всё время",
}


@dataclass(frozen=True, slots=True)
class Event:
    """Строка ленты."""

    at: datetime
    kind: Kind
    product: str  # код товара — по нему работает фильтр
    title: str  # человеческое название
    who: str
    amount: int | None  # None — денег не было вовсе
    status: str
    note: str = ""


@dataclass(slots=True)
class Filters:
    """Состояние фильтров; пустые множества значат «всё»."""

    period: str = "today"
    kinds: set[str] = field(default_factory=set)
    products: set[str] = field(default_factory=set)
    query: str = ""
    page: int = 1

    @property
    def since(self) -> datetime | None:
        now = datetime.now(UTC)
        if self.period == "today":
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if self.period == "7":
            return now - timedelta(days=7)
        if self.period == "30":
            return now - timedelta(days=30)
        return None

    def wants(self, kind: Kind, product: str) -> bool:
        if self.kinds and str(kind) not in self.kinds:
            return False
        return not (self.products and product not in self.products)


@dataclass(frozen=True, slots=True)
class Totals:
    """Итоги по текущей выборке, а не по всей базе."""

    events: int = 0
    money_in: int = 0
    money_back: int = 0
    deliveries: int = 0
    free_deliveries: int = 0

    @property
    def net(self) -> int:
        return self.money_in - self.money_back


def _who(user: User | None) -> str:
    if user is None:
        return "—"
    return f"@{user.username}" if user.username else f"id {user.telegram_id}"


def _tarot_status(reading) -> tuple[Kind, str]:
    status = ReadingStatus(reading.status)
    if status == ReadingStatus.READY:
        return Kind.DELIVERY, "готов"
    if status == ReadingStatus.FAILED:
        return Kind.TROUBLE, "упал"
    if status == ReadingStatus.PENDING_PAYMENT:
        return Kind.DRAFT, "не оплачен"
    return Kind.TROUBLE, "в работе"


def _ask_status(reading) -> tuple[Kind, str]:
    status = AskStatus(reading.status)
    if status == AskStatus.READY:
        return Kind.DELIVERY, "готов"
    if status == AskStatus.FAILED:
        return Kind.TROUBLE, "упал"
    if status == AskStatus.PENDING_PAYMENT:
        return Kind.DRAFT, "не оплачен"
    return Kind.TROUBLE, "в работе"


def _report_status(report, ready, failed) -> tuple[Kind, str]:
    if report.status == ready:
        return Kind.DELIVERY, "готов"
    if report.status == failed:
        return Kind.TROUBLE, "упал"
    return Kind.TROUBLE, "в работе"


async def product_titles(session: AsyncSession) -> dict[str, str]:
    """Каталог + продукты без товара — для фильтра и подписей строк."""
    rows = (await session.execute(select(Product.code, Product.title))).all()
    titles = {code: title for code, title in rows}
    for code, title in EXTRA_PRODUCTS.items():
        titles.setdefault(code, title)
    return titles


async def _users(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, User]:
    if not ids:
        return {}
    rows = (await session.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    return {user.id: user for user in rows}


def _matches_query(who: str, query: str) -> bool:
    return not query or query.lower().lstrip("@") in who.lower().lstrip("@")


async def collect(session: AsyncSession, filters: Filters) -> tuple[list[Event], Totals, int]:
    """События по фильтрам: страница, итоги и общее число строк."""
    since = filters.since
    titles = await product_titles(session)
    events: list[Event] = []

    def add(at, kind, product, who, amount, status, note=""):
        if at is None or not filters.wants(kind, product):
            return
        if not _matches_query(who, filters.query):
            return
        events.append(
            Event(
                at=at,
                kind=kind,
                product=product,
                title=titles.get(product, product),
                who=who,
                amount=amount,
                status=status,
                note=note,
            ),
        )

    # --- деньги: оплата и возврат это два разных события ---
    payment_rows = (
        await session.execute(
            select(Payment, User)
            .join(User, User.id == Payment.user_id)
            .where(*( [Payment.created_at >= since] if since else [] ))
            .order_by(Payment.created_at.desc()),
        )
    ).all()
    for payment, user in payment_rows:
        who = _who(user)
        add(payment.created_at, Kind.PAYMENT, payment.product_code, who, payment.amount, "оплачен",
            f"со скидкой −{payment.discount_percent}%" if payment.discount_percent else "")
        if payment.status == PaymentStatus.REFUNDED and payment.refunded_at:
            add(payment.refunded_at, Kind.REFUND, payment.product_code, who, payment.amount, "возвращён")

    # --- заказы: выдачи, черновики и аварии ---
    tarot_rows = (
        await session.execute(
            select(TarotReading, User)
            .join(User, User.id == TarotReading.user_id)
            .where(*( [TarotReading.created_at >= since] if since else [] ))
            .order_by(TarotReading.created_at.desc()),
        )
    ).all()
    for reading, user in tarot_rows:
        kind, status = _tarot_status(reading)
        add(reading.updated_at, kind, f"tarot_{reading.spread_type}", _who(user),
            reading.price_stars, status)

    ask_rows = (
        await session.execute(
            select(AskReading, User)
            .join(User, User.id == AskReading.user_id)
            .where(*( [AskReading.created_at >= since] if since else [] ))
            .order_by(AskReading.created_at.desc()),
        )
    ).all()
    for reading, user in ask_rows:
        kind, status = _ask_status(reading)
        add(reading.updated_at, kind, f"ask_{reading.question_key}", _who(user),
            reading.paid_amount, status)

    natal_rows = (
        await session.execute(
            select(NatalReport, User)
            .join(User, User.id == NatalReport.owner_user_id)
            .where(*( [NatalReport.created_at >= since] if since else [] ))
            .order_by(NatalReport.created_at.desc()),
        )
    ).all()
    for report, user in natal_rows:
        kind, status = _report_status(report, NatalReportStatus.READY, NatalReportStatus.FAILED)
        add(report.updated_at, kind, "natal_report", _who(user), None, status)

    compat_rows = (
        await session.execute(
            select(CompatibilityReport, User)
            .join(User, User.id == CompatibilityReport.owner_user_id)
            .where(*( [CompatibilityReport.created_at >= since] if since else [] ))
            .order_by(CompatibilityReport.created_at.desc()),
        )
    ).all()
    for report, user in compat_rows:
        kind, status = _report_status(report, ReportStatus.READY, ReportStatus.FAILED)
        add(report.updated_at, kind, "compatibility", _who(user), None, status)

    # --- бесплатные ежедневные: своих заказов у них нет, берём журнал ---
    daily_rows = (
        await session.execute(
            select(UsageEvent, User)
            .join(User, User.id == UsageEvent.user_id)
            .where(
                UsageEvent.action.in_([ACTION_DAY_CARD, ACTION_TAROT_DAILY]),
                *( [UsageEvent.created_at >= since] if since else [] ),
            )
            .order_by(UsageEvent.created_at.desc()),
        )
    ).all()
    for usage, user in daily_rows:
        add(usage.created_at, Kind.DELIVERY, usage.action, _who(user), None, "выдано")

    # --- колесо: судьба приза видна сразу ---
    spin_rows = (
        await session.execute(
            select(WheelWin, User)
            .join(User, User.id == WheelWin.user_id)
            .where(*( [WheelWin.created_at >= since] if since else [] ))
            .order_by(WheelWin.created_at.desc()),
        )
    ).all()
    now = datetime.now(UTC)
    for win, user in spin_rows:
        if win.activated_at is not None:
            status = "приз использован"
        elif win.expires_at is not None and win.expires_at < now:
            status = "приз сгорел"
        else:
            status = "приз ждёт"
        prize = titles.get(win.product_code, win.product_code)
        add(win.created_at, Kind.SPIN, "wheel_spin", _who(user), None, status,
            f"{prize} −{win.discount_percent}%")

    events.sort(key=lambda event: event.at, reverse=True)

    totals = Totals(
        events=len(events),
        money_in=sum(e.amount or 0 for e in events if e.kind is Kind.PAYMENT),
        money_back=sum(e.amount or 0 for e in events if e.kind is Kind.REFUND),
        deliveries=sum(1 for e in events if e.kind is Kind.DELIVERY),
        free_deliveries=sum(1 for e in events if e.kind is Kind.DELIVERY and not e.amount),
    )

    page = max(1, filters.page)
    start = (page - 1) * PAGE_SIZE
    return events[start : start + PAGE_SIZE], totals, len(events)
