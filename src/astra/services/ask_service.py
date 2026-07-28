"""Пайплайн ответов «Спроси Астрид».

Разделение обязанностей жёсткое:
- расчёт (числа и факторы) считается в момент оплаты, синхронно — он быстрый
  (десятки миллисекунд) и должен попасть в БД до того, как что-то уйдёт в очередь;
- разбор пишет worker через LLM: он медленный, его ждём с драматургией в чате;
- если разбор не собрался — звёзды возвращаются автоматически.

Так карточка с числом уходит человеку сразу после оплаты, а текст догоняет.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from astra.ask import models as ask_crud
from astra.ask.enums import AskStatus
from astra.ask.models import AskReading
from astra.ask.products import get_product
from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger
from astra.llm.types import ChatMessage, CompletionRequest
from astra.services.astro_service import build_full_chart_for_user
from astra.users import crud as users_crud
from astra.users.models import User

log = get_logger(__name__)


_GENERATE_ATTEMPTS = 3

ASK_FAILED_REFUNDED_TEXT = (
    "Не получилось собрать разбор — звёзды вернулись на твой счёт ⭐\n"
    "Попробуй ещё раз чуть позже, я буду рядом 💜"
)
ASK_FAILED_TEXT = (
    "Не получилось собрать разбор. Мы уже разбираемся, звёзды вернём — "
    "напиши нам, если что-то пойдёт не так 💜"
)


def calibration_answer(reading: AskReading) -> bool:
    """Ответ человека на калибрующий вопрос продукта.

    Первый продукт («судьбоносные партнёры») писал его в отдельную колонку —
    её и читаем для старых строк; остальные продукты кладут в `context`.
    """
    product = get_product(reading.question_key)
    if product is not None and reading.context:
        value = reading.context.get(product.calibration_field)
        if value is not None:
            return bool(value)
    return bool(reading.in_relationship)


async def compute_for_reading(
    session: AsyncSession,
    reading: AskReading,
    user: User,
) -> BaseModel | None:
    """Посчитать факты по карте пользователя. None — нет данных для расчёта."""
    product = get_product(reading.question_key)
    profile = user.profile
    if product is None or profile is None or profile.birth_date is None:
        return None
    chart = await build_full_chart_for_user(session, user, profile)
    result = product.compute(chart, profile.birth_date, calibration_answer(reading), None)
    log.info(
        Event.ASK_ANSWER_COMPUTED,
        reading_id=reading.id,
        question_key=reading.question_key,
        methodology_version=product.methodology_version,
    )
    return result


def result_from_reading(reading: AskReading) -> BaseModel | None:
    """Снимок расчёта из БД обратно в схему продукта."""
    product = get_product(reading.question_key)
    if product is None or not reading.computed:
        return None
    return product.result_model.model_validate(reading.computed)


async def generate_ask_answer(
    session: AsyncSession,
    reading_id: UUID,
    settings: Settings | None = None,
) -> AskReading | None:
    """Разбор поверх посчитанных чисел. None — ответ помечен failed."""
    cfg = settings or get_settings()
    reading = await ask_crud.get_reading(session, reading_id)
    if reading is None:
        return None
    if reading.answer and reading.status == AskStatus.READY:
        return reading  # идемпотентность при requeue

    product = get_product(reading.question_key)
    result = result_from_reading(reading)
    if product is None or result is None:
        await ask_crud.mark_failed(session, reading, "missing_computed")
        return None

    user = await users_crud.get_user_by_id(session, reading.user_id)
    profile = user.profile if user else None
    prompt = product.prompt

    from astra.llm.daily_llm import get_daily_provider

    provider = get_daily_provider(cfg)
    extra: dict = {"json_mode": True}
    if provider.name == "deepseek":
        extra["thinking_disabled"] = True
    request = CompletionRequest(
        messages=(
            ChatMessage("system", prompt.SYSTEM_PROMPT),
            ChatMessage(
                "user",
                prompt.build_user_message(
                    result,
                    user_name=profile.display_name if profile else None,
                    gender=profile.gender if profile else None,
                ),
            ),
        ),
        temperature=prompt.TEMPERATURE,
        max_tokens=prompt.MAX_TOKENS,
        timeout_seconds=cfg.deepseek_timeout_seconds,
        extra=extra,
    )

    expected = product.validate_expected(result)
    last_error = "unknown"
    for _ in range(_GENERATE_ATTEMPTS):
        completion = await provider.complete(request)
        if not completion.text:
            last_error = completion.reason or "empty_response"
            continue
        answer = prompt.parse(completion.text)
        if answer is None:
            last_error = "json_invalid"
            continue
        validation_error = prompt.validate(answer, expected)
        if validation_error is not None:
            last_error = validation_error
            continue
        payload = answer.model_dump()
        payload["html"] = prompt.render_answer(answer, result)
        await ask_crud.save_answer(session, reading, payload)
        log.info(Event.ASK_ANSWER_GENERATED, reading_id=reading.id)
        return reading

    await ask_crud.mark_failed(session, reading, last_error)
    log.error(Event.ASK_ANSWER_FAILED, reading_id=reading.id, reason=last_error)
    return None


async def deliver_ask_answer(
    session: AsyncSession,
    reading: AskReading,
    settings: Settings | None = None,
) -> bool:
    """Отправить готовый разбор с кнопками под ним."""
    from astra.telegram.ask_keyboards import ask_answer_keyboard
    from astra.workers.telegram_send import send_telegram_html

    user = await users_crud.get_user_by_id(session, reading.user_id)
    if user is None or not reading.answer:
        return False
    html_text = reading.answer.get("html")
    if not html_text:
        return False
    referral_code = user.referral_code.code if user.referral_code else None
    await send_telegram_html(
        user.telegram_id,
        html_text,
        settings,
        reply_markup=ask_answer_keyboard(reading, referral_code=referral_code),
    )
    log.info(Event.ASK_ANSWER_SENT, reading_id=reading.id, user_id=user.id)
    return True


async def refund_ask_payment(
    session: AsyncSession,
    reading: AskReading,
    telegram_id: int,
    settings: Settings | None = None,
) -> bool:
    """Вернуть звёзды за несобравшийся разбор. Идемпотентно."""
    from astra.payments.service import refund_star_payment_api

    if not reading.charge_id or reading.refunded:
        return False
    try:
        await refund_star_payment_api(telegram_id, reading.charge_id, settings)
    except Exception as exc:
        log.error(
            Event.PAYMENT_REFUND_FAILED,
            reading_id=reading.id,
            charge_id=reading.charge_id,
            error_type=type(exc).__name__,
        )
        return False
    await ask_crud.mark_refunded(session, reading)
    return True


async def notify_ask_failed(
    session: AsyncSession,
    reading: AskReading,
    *,
    refunded: bool,
    settings: Settings | None = None,
) -> None:
    from astra.workers.telegram_send import send_telegram_html

    user = await users_crud.get_user_by_id(session, reading.user_id)
    if user is None:
        return
    text = ASK_FAILED_REFUNDED_TEXT if refunded else ASK_FAILED_TEXT
    await send_telegram_html(user.telegram_id, text, settings)
