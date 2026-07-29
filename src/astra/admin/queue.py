"""Очередь проблем: заказы, которые не дошли до человека.

Три случая, и они лечатся по-разному:

* **упал** — статус `failed`. Воркер уже отработал свои попытки; за платные
  продукты звёзды он вернул сам. Здесь такой заказ виден вместе с причиной,
  чтобы понять, чинить продукт или это разовая осечка LLM.
* **завис** — статус «в работе» дольше `STUCK_AFTER_MINUTES`. Вот это самое
  опасное: воркер по какой-то причине не дошёл до конца и не поставил
  `failed`, поэтому автоматический возврат не сработал. Человек заплатил и
  не получил ничего, и никто об этом не узнает, пока он не напишет.
* **сирота** — оплата есть, а заказа к ней нет.

Действия сделаны так, чтобы панель осталась переносимой в отдельный сервис:
повтор публикует задачу в RabbitMQ, возврат зовёт Bot API напрямую
(`refund_star_payment_api`). Ни aiogram, ни хендлеров бота здесь нет.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.admin.service import AdminError
from astra.ask import models as ask_crud
from astra.ask.enums import AskStatus
from astra.ask.models import AskReading
from astra.compatibility.enums import COMPATIBILITY_IN_FLIGHT_STATUSES, ReportStatus
from astra.compatibility.models import CompatibilityReport
from astra.core.observability import get_logger
from astra.messaging.publisher import publish_ask_answer_generate, publish_tarot_reading_generate
from astra.natal_report.enums import NATAL_IN_FLIGHT_STATUSES, NatalReportStatus
from astra.natal_report.models import NatalReport
from astra.payments import models as payments_crud
from astra.payments.enums import PaymentStatus
from astra.payments.models import Payment
from astra.payments.service import refund_star_payment_api
from astra.services.compatibility_pipeline import resume_compatibility_pipeline
from astra.services.natal_pipeline import resume_natal_pipeline
from astra.tarot.enums import READING_IN_FLIGHT_STATUSES, ReadingStatus
from astra.tarot.models import TarotReading
from astra.users.models import User

log = get_logger(__name__)

# Столько ждём воркера, прежде чем считать заказ зависшим. Генерация с LLM
# укладывается в пару минут; всё, что висит дольше, уже не доедет само.
STUCK_AFTER_MINUTES = 15


class Trouble(StrEnum):
    FAILED = "failed"
    STUCK = "stuck"
    ORPHAN = "orphan"


class Target(StrEnum):
    """Что чиним — от этого зависят и повтор, и возврат."""

    TAROT = "tarot"
    ASK = "ask"
    NATAL = "natal"
    COMPATIBILITY = "compatibility"
    PAYMENT = "payment"


_TITLES = {
    Target.TAROT: "Таро",
    Target.ASK: "Спроси Астрид",
    Target.NATAL: "Натал",
    Target.COMPATIBILITY: "Совместимость",
    Target.PAYMENT: "Оплата без заказа",
}


@dataclass(frozen=True, slots=True)
class Problem:
    """Строка очереди: что сломалось, у кого и что с этим можно сделать."""

    trouble: Trouble
    target: Target
    entity_id: uuid.UUID
    product: str
    who: str
    telegram_id: int | None
    amount: int | None
    status: str
    since: datetime
    reason: str
    can_retry: bool
    can_refund: bool

    @property
    def age(self) -> timedelta:
        return datetime.now(UTC) - self.since

    @property
    def age_human(self) -> str:
        minutes = int(self.age.total_seconds() // 60)
        if minutes < 60:
            return f"{minutes} мин"
        hours = minutes // 60
        if hours < 24:
            return f"{hours} ч"
        return f"{hours // 24} дн"


def _who(user: User | None) -> tuple[str, int | None]:
    if user is None:
        return "—", None
    return (f"@{user.username}" if user.username else f"id {user.telegram_id}"), user.telegram_id


def _stuck_before() -> datetime:
    return datetime.now(UTC) - timedelta(minutes=STUCK_AFTER_MINUTES)


async def _tarot_problems(session: AsyncSession) -> list[Problem]:
    in_flight = [str(status) for status in READING_IN_FLIGHT_STATUSES]
    rows = (
        await session.execute(
            select(TarotReading, User)
            .join(User, User.id == TarotReading.user_id)
            .where(
                or_(
                    TarotReading.status == ReadingStatus.FAILED,
                    TarotReading.status.in_(in_flight),
                ),
            )
            .order_by(TarotReading.updated_at.desc()),
        )
    ).all()

    problems: list[Problem] = []
    for reading, user in rows:
        stuck = reading.status != ReadingStatus.FAILED
        if stuck and reading.updated_at > _stuck_before():
            continue  # ещё в работе, это нормально
        who, telegram_id = _who(user)
        problems.append(
            Problem(
                trouble=Trouble.STUCK if stuck else Trouble.FAILED,
                target=Target.TAROT,
                entity_id=reading.id,
                product=f"Таро · {reading.spread_type}",
                who=who,
                telegram_id=telegram_id,
                amount=reading.price_stars,
                status=reading.status,
                since=reading.updated_at,
                reason=reading.failure_reason or ("воркер не ответил" if stuck else "причина не записана"),
                can_retry=True,
                can_refund=bool(reading.price_stars),
            ),
        )
    return problems


async def _ask_problems(session: AsyncSession) -> list[Problem]:
    rows = (
        await session.execute(
            select(AskReading, User)
            .join(User, User.id == AskReading.user_id)
            .where(AskReading.status.in_([AskStatus.FAILED, AskStatus.GENERATING]))
            .order_by(AskReading.updated_at.desc()),
        )
    ).all()

    problems: list[Problem] = []
    for reading, user in rows:
        stuck = reading.status == AskStatus.GENERATING
        if stuck and reading.updated_at > _stuck_before():
            continue
        who, telegram_id = _who(user)
        problems.append(
            Problem(
                trouble=Trouble.STUCK if stuck else Trouble.FAILED,
                target=Target.ASK,
                entity_id=reading.id,
                product=f"Спроси Астрид · {reading.question_key}",
                who=who,
                telegram_id=telegram_id,
                amount=reading.paid_amount,
                status=reading.status,
                since=reading.updated_at,
                reason=reading.error or ("воркер не ответил" if stuck else "причина не записана"),
                can_retry=True,
                can_refund=bool(reading.charge_id) and not reading.refunded,
            ),
        )
    return problems


async def _report_problems(
    session: AsyncSession,
    model,
    target: Target,
    failed_status,
    in_flight,
) -> list[Problem]:
    """Натал и совместимость устроены одинаково: статус + failure_reason."""
    rows = (
        await session.execute(
            select(model, User)
            .join(User, User.id == model.owner_user_id)
            .where(or_(model.status == failed_status, model.status.in_([str(s) for s in in_flight])))
            .order_by(model.updated_at.desc()),
        )
    ).all()

    problems: list[Problem] = []
    for report, user in rows:
        stuck = report.status != failed_status
        if stuck and report.updated_at > _stuck_before():
            continue
        who, telegram_id = _who(user)
        problems.append(
            Problem(
                trouble=Trouble.STUCK if stuck else Trouble.FAILED,
                target=target,
                entity_id=report.id,
                product=_TITLES[target],
                who=who,
                telegram_id=telegram_id,
                amount=None,  # бесплатные продукты — возвращать нечего
                status=report.status,
                since=report.updated_at,
                reason=report.failure_reason or ("воркер не ответил" if stuck else "причина не записана"),
                can_retry=True,
                can_refund=False,
            ),
        )
    return problems


async def _orphan_payments(session: AsyncSession) -> list[Problem]:
    """Оплата прошла, а заказа к ней нет.

    Таро: платёж хранит `reading_id`, поэтому пустая ссылка и есть сирота.
    «Спроси Астрид»: связь обратная — charge_id лежит на самом ответе, так
    что ищем платежи, чей charge не встречается ни в одном ответе.
    """
    ask_charges = select(AskReading.charge_id).where(AskReading.charge_id.isnot(None))
    rows = (
        await session.execute(
            select(Payment, User)
            .join(User, User.id == Payment.user_id)
            .where(
                Payment.status == PaymentStatus.COMPLETED,
                or_(
                    (Payment.product_code.like("tarot_%")) & (Payment.reading_id.is_(None)),
                    (Payment.product_code.like("ask_%"))
                    & (Payment.provider_charge_id.notin_(ask_charges)),
                ),
            )
            .order_by(Payment.created_at.desc()),
        )
    ).all()

    problems = []
    for payment, user in rows:
        who, telegram_id = _who(user)
        problems.append(
            Problem(
                trouble=Trouble.ORPHAN,
                target=Target.PAYMENT,
                entity_id=payment.id,
                product=payment.product_code,
                who=who,
                telegram_id=telegram_id,
                amount=payment.amount,
                status=payment.status,
                since=payment.created_at,
                reason="оплата прошла, заказ к ней не привязался",
                can_retry=False,  # заказ нечем восстановить — только вернуть деньги
                can_refund=True,
            ),
        )
    return problems


async def list_problems(session: AsyncSession) -> list[Problem]:
    """Всё, что требует внимания, — старое сверху: оно ждёт дольше всех."""
    problems = (
        await _tarot_problems(session)
        + await _ask_problems(session)
        + await _report_problems(
            session, NatalReport, Target.NATAL, NatalReportStatus.FAILED, NATAL_IN_FLIGHT_STATUSES,
        )
        + await _report_problems(
            session,
            CompatibilityReport,
            Target.COMPATIBILITY,
            ReportStatus.FAILED,
            COMPATIBILITY_IN_FLIGHT_STATUSES,
        )
        + await _orphan_payments(session)
    )
    return sorted(problems, key=lambda problem: problem.since)


@dataclass(frozen=True, slots=True)
class Summary:
    total: int = 0
    stuck: int = 0
    money_at_risk: int = 0
    oldest: str = "—"


def summarize(problems: list[Problem]) -> Summary:
    if not problems:
        return Summary()
    return Summary(
        total=len(problems),
        stuck=sum(1 for problem in problems if problem.trouble is Trouble.STUCK),
        money_at_risk=sum(problem.amount or 0 for problem in problems),
        oldest=problems[0].age_human,
    )


async def retry(session: AsyncSession, target: Target, entity_id: uuid.UUID) -> str:
    """Поставить заказ обратно в очередь генерации. Возвращает текст для экрана."""
    if target is Target.TAROT:
        reading = await session.get(TarotReading, entity_id)
        if reading is None:
            raise AdminError("Расклад не найден.")
        await publish_tarot_reading_generate(reading.id)
        product = f"Таро · {reading.spread_type}"
    elif target is Target.ASK:
        reading = await session.get(AskReading, entity_id)
        if reading is None:
            raise AdminError("Ответ не найден.")
        await publish_ask_answer_generate(reading.id)
        product = f"Спроси Астрид · {reading.question_key}"
    elif target is Target.NATAL:
        report = await session.get(NatalReport, entity_id)
        if report is None:
            raise AdminError("Разбор не найден.")
        await resume_natal_pipeline(report)
        product = "Натал"
    elif target is Target.COMPATIBILITY:
        report = await session.get(CompatibilityReport, entity_id)
        if report is None:
            raise AdminError("Разбор не найден.")
        await resume_compatibility_pipeline(report)
        product = "Совместимость"
    else:
        raise AdminError("Оплату без заказа перезапустить нельзя — только вернуть деньги.")

    log.info("admin.queue.retried", target=str(target), entity_id=str(entity_id))
    return f"{product}: задача снова в очереди."


async def _refund_charge(
    session: AsyncSession,
    telegram_id: int,
    charge_id: str,
) -> None:
    """Вернуть звёзды и пометить платёж возвращённым."""
    try:
        await refund_star_payment_api(telegram_id, charge_id)
    except Exception as exc:  # noqa: BLE001 — текст ошибки уходит на экран
        log.error("admin.queue.refund_failed", charge_id=charge_id, error_type=type(exc).__name__)
        raise AdminError(f"Telegram не принял возврат: {type(exc).__name__}.") from exc

    payment = await payments_crud.get_payment_by_charge(
        session,
        "telegram_stars",
        charge_id,
    )
    if payment is not None and payment.status != PaymentStatus.REFUNDED:
        await payments_crud.mark_payment_refunded(session, payment)


async def refund(session: AsyncSession, target: Target, entity_id: uuid.UUID) -> str:
    """Вернуть человеку звёзды. Идемпотентно: повторный возврат не проходит."""
    if target is Target.TAROT:
        reading = await session.get(TarotReading, entity_id)
        if reading is None:
            raise AdminError("Расклад не найден.")
        payment = await payments_crud.get_completed_payment_for_reading(session, reading.id)
        if payment is None:
            raise AdminError("По этому раскладу нет оплаты — возвращать нечего.")
        user = await session.get(User, reading.user_id)
        await _refund_charge(session, user.telegram_id, payment.provider_charge_id)
        amount = payment.amount

    elif target is Target.ASK:
        reading = await session.get(AskReading, entity_id)
        if reading is None:
            raise AdminError("Ответ не найден.")
        if reading.refunded:
            raise AdminError("Звёзды за этот ответ уже возвращены.")
        if not reading.charge_id:
            raise AdminError("У ответа нет платежа — возвращать нечего.")
        user = await session.get(User, reading.user_id)
        await _refund_charge(session, user.telegram_id, reading.charge_id)
        await ask_crud.mark_refunded(session, reading)
        amount = reading.paid_amount

    elif target is Target.PAYMENT:
        payment = await session.get(Payment, entity_id)
        if payment is None:
            raise AdminError("Платёж не найден.")
        if payment.status == PaymentStatus.REFUNDED:
            raise AdminError("Этот платёж уже возвращён.")
        user = await session.get(User, payment.user_id)
        await _refund_charge(session, user.telegram_id, payment.provider_charge_id)
        amount = payment.amount

    else:
        raise AdminError("Этот продукт бесплатный — возвращать нечего.")

    log.info("admin.queue.refunded", target=str(target), entity_id=str(entity_id), amount=amount)
    return f"Возврат прошёл: {amount} ⭐ вернулись человеку."
