"""Страховка обработчиков `successful_payment`: деньги не теряются, если код упал.

Когда приходит `successful_payment`, Telegram звёзды уже списал. Исключение в
обработчике откатывает сессию (`DbSessionMiddleware`) — платёж не записан,
человек остался без продукта и без денег. Этот модуль закрывает дыру.

Как пользоваться (обработчик, который не знает про Колесо, таро или «Спроси»):

    async with payment_guard(
        message,
        session,
        user_id=user.id,                 # UUID пользователя в базе
        telegram_id=message.from_user.id,
        payload=payment_info.invoice_payload,
        charge_id=payment_info.telegram_payment_charge_id,
        reason="wheel_spin",             # метка продукта для лога
        refunded_text=_REFUND_TEXT,      # что сказать, когда звёзды вернулись
    ) as guard:
        with guard.recording():
            # Фаза записи: всё, что должно лечь в базу одной транзакцией —
            # запись платежа, списание со счёта, создание продукта, commit.
            ...
        # Сюда доходим только после успешной записи: платёж записан.
        guard.after_record_text = "текст продукта простым текстом"
        await показать_продукт_красиво(...)

Две фазы, граница явная:

* **До записи** (исключение внутри `with guard.recording()`): сессия
  обработчика откатывается, а в отдельной сессии снимается бронь счёта
  (`cancel_charge`); Telegram-платёж возвращается (`refund_star_payment`);
  человеку уходит `refunded_text`; в лог — `Event.PAYMENT_ORPHAN` с `reason`
  и трейсом, в Sentry — исключение. Исключение дальше не летит. Если сам
  возврат не удался, человеку говорим об этом честно (`REFUND_FAILED_TEXT`),
  а в лог идёт `Event.PAYMENT_REFUND_FAILED`.
* **После записи** (исключение вне `recording()`, после его нормального
  выхода): продукт уже в базе, деньги НЕ возвращаются. Человеку уходит
  `guard.after_record_text` простым сообщением (если обработчик успел его
  задать); в лог и Sentry — событие. Исключение дальше не летит.

`return` внутри `recording()` считается нормальным выходом: дубль платежа
(`IntegrityError`, `None` от регистрации) — это «платёж уже записан».
Внутренняя часть цены (кошелёк) держится бронью: `settle_charge` вызывается
внутри `recording()` в той же транзакции, что и запись платежа, поэтому откат
вернёт её сам, а `cancel_charge` снимает бронь, которую откат не тронул.
`CancelledError` и прочие `BaseException` защита не глотает.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from uuid import UUID

from aiogram.types import InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.observability import Event, get_logger
from astra.core.sentry import capture_exception
from astra.db.session import get_session_factory
from astra.services.wallet_service import cancel_charge
from astra.telegram.keyboards import support_contextual_keyboard

log = get_logger(__name__)

REFUND_FAILED_TEXT = (
    "Оплата прошла, но я не смогла её обработать и вернуть звёзды сразу. "
    "Напиши в поддержку — я всё улажу 💬"
)


class PaymentGuard:
    """Состояние защиты: записан ли платёж и что сказать, если сломается оформление."""

    def __init__(
        self,
        message: Message,
        session: AsyncSession,
        *,
        user_id: UUID,
        telegram_id: int,
        payload: str,
        charge_id: str,
        reason: str,
        refunded_text: str,
    ) -> None:
        self.message = message
        self.session = session
        self.user_id = user_id
        self.telegram_id = telegram_id
        self.payload = payload
        self.charge_id = charge_id
        self.reason = reason
        self.refunded_text = refunded_text
        self.recorded = False
        # Простой текст для человека, если оформление после записи сломается.
        self.after_record_text: str | None = None

    @contextmanager
    def recording(self) -> Iterator[None]:
        """Фаза записи: нормальный выход = платёж записан, возврат больше не нужен."""
        yield
        self.recorded = True

    async def _say(self, text: str, *, reply_markup: InlineKeyboardMarkup | None = None) -> None:
        try:
            await self.message.answer(text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception as exc:
            log.exception(Event.TELEGRAM_API_FAILED, reason=f"{self.reason}_guard_notify")
            capture_exception(exc)

    async def undo_unrecorded(self, exc: Exception) -> None:
        """Платёж не записан: вернуть всё и сказать об этом."""
        log.exception(
            Event.PAYMENT_ORPHAN,
            reason=f"{self.reason}_failed_before_record",
            charge_id=self.charge_id,
            user_id=self.user_id,
        )
        capture_exception(exc)
        try:
            await self.session.rollback()
        except Exception as rollback_exc:
            log.exception(Event.PAYMENT_ORPHAN, reason=f"{self.reason}_rollback_failed")
            capture_exception(rollback_exc)

        refunded = False
        bot = self.message.bot
        try:
            if bot is None:
                msg = "у сообщения нет бота — возврат невозможен"
                raise RuntimeError(msg)  # noqa: TRY301
            await bot.refund_star_payment(
                user_id=self.telegram_id,
                telegram_payment_charge_id=self.charge_id,
            )
            refunded = True
        except Exception as refund_exc:
            log.exception(
                Event.PAYMENT_REFUND_FAILED,
                reason=self.reason,
                charge_id=self.charge_id,
            )
            capture_exception(refund_exc)

        # Своя сессия: сессия обработчика откачена и, возможно, сломана.
        try:
            async with get_session_factory()() as fresh:
                await cancel_charge(fresh, self.user_id, self.payload)
                await fresh.commit()
        except Exception as cancel_exc:
            log.exception(Event.PAYMENT_ORPHAN, reason=f"{self.reason}_cancel_hold_failed")
            capture_exception(cancel_exc)

        if refunded:
            await self._say(self.refunded_text)
        else:
            await self._say(REFUND_FAILED_TEXT, reply_markup=support_contextual_keyboard())

    async def deliver_after_record(self, exc: Exception) -> None:
        """Платёж записан, сломалось оформление: деньги остаются, продукт — текстом."""
        log.exception(
            Event.TELEGRAM_UPDATE_FAILED,
            reason=f"{self.reason}_failed_after_record",
            charge_id=self.charge_id,
            user_id=self.user_id,
        )
        capture_exception(exc)
        if self.after_record_text is not None:
            await self._say(self.after_record_text)


@asynccontextmanager
async def payment_guard(
    message: Message,
    session: AsyncSession,
    *,
    user_id: UUID,
    telegram_id: int,
    payload: str,
    charge_id: str,
    reason: str,
    refunded_text: str,
) -> AsyncIterator[PaymentGuard]:
    """Обернуть обработчик `successful_payment`; см. докстринг модуля."""
    guard = PaymentGuard(
        message,
        session,
        user_id=user_id,
        telegram_id=telegram_id,
        payload=payload,
        charge_id=charge_id,
        reason=reason,
        refunded_text=refunded_text,
    )
    try:
        yield guard
    except Exception as exc:
        if guard.recorded:
            await guard.deliver_after_record(exc)
        else:
            await guard.undo_unrecorded(exc)
