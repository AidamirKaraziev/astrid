"""Экран «Звёзды»: настоящий баланс Telegram против внутреннего кошелька.

Две половины считаются из разных источников, и складывать их нельзя.

**Telegram** — деньги, которые действительно пришли. Спрашиваются у Bot API
(`getMyStarBalance`, `getStarTransactions`), своей копии мы не держим: Telegram
и так знает точный ответ, а вторая правда рядом с первой быстро расходится.
Зовём по HTTP, а не через aiogram: панель едет отдельным процессом, в котором
бота нет, и импорт `astra.telegram` затянул бы в неё хендлеры с клавиатурами.

**Внутренний кошелёк** — обязательство. Он печатает звёзды бесплатно: награда
за приглашённого, приветствие новичку, подарок. В выручке их нет и не было,
но однажды человек потратит их вместо оплаты. Поэтому напечатанное считается
отдельно от потраченного, а разница — то, что ещё лежит на счетах и ждёт.

Печать различается по началу `payload`, а не по причине: награда, приветствие
и подарок носят в леджере одну и ту же `REFERRAL_REWARD`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.observability import Event, get_logger
from astra.payments.service import call_bot_api
from astra.wallet.crud import total_outstanding
from astra.wallet.models import StarWalletEntry, WalletReason

log = get_logger(__name__)

# Сколько последних операций Telegram показываем. Больше сотни лента не несёт
# смысла: за деталями идут в «Платежи», здесь нужен масштаб.
TRANSACTIONS_LIMIT = 50

REWARD_PREFIX = "ref_reward:"
WELCOME_PREFIX = "ref_welcome:"
GIFT_PREFIX = "gift:"


@dataclass(frozen=True, slots=True)
class Transaction:
    """Одна операция со звёздами на стороне Telegram."""

    at: datetime
    amount: int
    incoming: bool
    counterparty: str


@dataclass(frozen=True, slots=True)
class TelegramStars:
    """Что показывает Bot API. `error` — не ответил, цифрам верить нельзя."""

    balance: int = 0
    incoming: int = 0
    outgoing: int = 0
    transactions: tuple[Transaction, ...] = ()
    error: str | None = None

    @property
    def alive(self) -> bool:
        return self.error is None


@dataclass(frozen=True, slots=True)
class Wallet:
    """Внутренний кошелёк: что напечатано даром и сколько из этого ушло."""

    rewards: int = 0
    welcome: int = 0
    gifts: int = 0
    other: int = 0
    spent: int = 0
    outstanding: int = 0

    @property
    def minted(self) -> int:
        return self.rewards + self.welcome + self.gifts + self.other


@dataclass(frozen=True, slots=True)
class Stars:
    telegram: TelegramStars
    wallet: Wallet


def _counterparty(partner: dict) -> str:
    """Кто на том конце. У партнёра-человека есть `user`, у прочих — только тип."""
    user = (partner or {}).get("user")
    if user:
        username = user.get("username")
        return f"@{username}" if username else str(user.get("id", "—"))
    return (partner or {}).get("type", "—")


async def telegram_stars(limit: int = TRANSACTIONS_LIMIT) -> TelegramStars:
    """Баланс и последние операции у Telegram.

    Отказ Bot API не роняет страницу: внутренняя половина экрана считается по
    своей базе и остаётся верной, даже когда до Telegram не достучаться.
    """
    try:
        balance = await call_bot_api("getMyStarBalance")
        page = await call_bot_api("getStarTransactions", {"limit": limit})
    except Exception as exc:
        log.warning(Event.TELEGRAM_API_FAILED, method="stars", reason=str(exc))
        return TelegramStars(error=str(exc))

    rows = []
    incoming = outgoing = 0
    for item in page.get("transactions", []):
        source = item.get("source")
        amount = int(item.get("amount", 0))
        if source is not None:
            incoming += amount
        else:
            outgoing += amount
        rows.append(
            Transaction(
                at=datetime.fromtimestamp(item.get("date", 0), tz=UTC),
                amount=amount,
                incoming=source is not None,
                counterparty=_counterparty(source or item.get("receiver")),
            ),
        )
    return TelegramStars(
        balance=int(balance.get("amount", 0)),
        incoming=incoming,
        outgoing=outgoing,
        transactions=tuple(rows),
    )


async def wallet_liability(session: AsyncSession) -> Wallet:
    """Сколько звёзд напечатано даром, сколько потрачено и сколько ещё висит."""
    positive = StarWalletEntry.delta > 0

    def minted_where(prefix: str):
        return func.coalesce(
            func.sum(
                case(
                    (positive & StarWalletEntry.payload.startswith(prefix), StarWalletEntry.delta),
                    else_=0,
                ),
            ),
            0,
        )

    # «Прочее» — миграция баллов и ручные начисления: печать без повода со
    # стороны человека, но в обязательствах она такая же.
    other = func.coalesce(
        func.sum(
            case(
                (
                    positive
                    & StarWalletEntry.reason.in_(
                        [WalletReason.POINTS_MIGRATION, WalletReason.MANUAL],
                    ),
                    StarWalletEntry.delta,
                ),
                else_=0,
            ),
        ),
        0,
    )
    spent = func.coalesce(
        func.sum(
            case(
                (StarWalletEntry.reason == WalletReason.PURCHASE, -StarWalletEntry.delta),
                else_=0,
            ),
        ),
        0,
    )
    row = (
        await session.execute(
            select(
                minted_where(REWARD_PREFIX),
                minted_where(WELCOME_PREFIX),
                minted_where(GIFT_PREFIX),
                other,
                spent,
            ),
        )
    ).one()

    return Wallet(*(int(value) for value in row), outstanding=await total_outstanding(session))


async def collect(session: AsyncSession) -> Stars:
    return Stars(
        telegram=await telegram_stars(),
        wallet=await wallet_liability(session),
    )
