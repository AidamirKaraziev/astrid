from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from astra.predictions import crud as predictions_crud
from astra.predictions.models import Prediction
from astra.predictions.status import PredictionStatus
from astra.services.prediction_pending import (
    clear_prediction_pending,
    is_prediction_pending,
    try_mark_prediction_pending,
)
from astra.services.prediction_pipeline import (
    enqueue_prediction_pipeline,
    resume_prediction_pipeline,
)
from astra.users.models import Profile, User


class PredictionRequestStatus(StrEnum):
    READY = "ready"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PredictionRequestOutcome:
    status: PredictionRequestStatus
    prediction: Prediction | None = None


def format_prediction_message(
    profile: Profile,
    body: str,
    *,
    points: int = 0,
    streak: int = 0,
) -> str:
    """Текст предсказания для отправки в Telegram (без обёртки)."""
    del profile, points, streak
    return body.strip()


_RU_MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)

_SPHERE_EMOJI: dict[int, str] = {
    1: "🌱", 2: "💰", 3: "💬", 4: "🏠", 5: "🎨", 6: "🩺",
    7: "🤝", 8: "🔑", 9: "🧭", 10: "💼", 11: "🌐", 12: "🌊",
}


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _split_v4_blocks(text: str) -> tuple[str, str, str] | None:
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    if len(blocks) < 3:
        return None
    return blocks[0], blocks[1], " ".join(blocks[2:])


def format_compass_message(prediction: Prediction) -> str | None:
    """HTML «Компаса дня» из контекста v2 + трёх блоков LLM; None — не v2."""
    ctx = prediction.astro_context or {}
    if ctx.get("schema_version") != 2:
        return None
    body = (prediction.text or "").strip()
    blocks = _split_v4_blocks(body)
    if blocks is None:
        return None
    question, forecast, step = blocks

    target = date.fromisoformat(str(ctx["date"]))
    header = f"{target.day} {_RU_MONTHS_GENITIVE[target.month - 1]}"
    moon = ctx.get("moon") or {}
    if moon.get("sign"):
        from astra.astro.constants import SIGN_RU_PREPOSITIONAL

        sign = SIGN_RU_PREPOSITIONAL.get(str(moon["sign"]), str(moon["sign"]))
        header += f" · Луна в {sign}"
        if moon.get("phase"):
            header += f", {moon['phase']}"

    lines = [
        f"🌙 <b>{_escape_html(header)}</b>",
        "",
        f"<i>{_escape_html(question)}</i>",
        "",
        _escape_html(forecast),
    ]

    sphere = ctx.get("sphere_of_day")
    if sphere and sphere.get("label"):
        emoji = _SPHERE_EMOJI.get(int(sphere.get("house") or 0), "✨")
        lines += ["", f"{emoji} <b>Сфера дня:</b> {_escape_html(str(sphere['label']))}"]

    lines += ["", f"→ <b>Один шаг:</b> {_escape_html(step)}"]
    return "\n".join(lines)


def format_zodiac_daily_message(prediction: Prediction) -> str | None:
    """HTML общего гороскопа по знаку (тариф без персональных); None — не zodiac."""
    ctx = prediction.astro_context or {}
    if ctx.get("schema_version") != "zodiac":
        return None
    body = (prediction.text or "").strip()
    if not body:
        return None

    from astra.predictions.zodiac_daily import ZODIAC_CTA

    target = date.fromisoformat(str(ctx["date"]))
    header = f"{target.day} {_RU_MONTHS_GENITIVE[target.month - 1]} · {ctx.get('sign', '')}"
    if ctx.get("moon_note"):
        header += f" · {ctx['moon_note']}"

    blocks = _split_v4_blocks(body)
    if blocks is not None:
        question, forecast, step = blocks
        body_html = (
            f"<i>{_escape_html(question)}</i>\n\n"
            f"{_escape_html(forecast)}\n\n"
            f"→ <b>Один шаг:</b> {_escape_html(step)}"
        )
    else:
        body_html = _escape_html(body)

    return f"🌙 <b>{_escape_html(header)}</b>\n\n{body_html}\n\n{ZODIAC_CTA}"


def format_prediction_for_user(
    prediction: Prediction,
    user: User,
    profile: Profile,
) -> str:
    del user, profile
    zodiac = format_zodiac_daily_message(prediction)
    if zodiac is not None:
        return zodiac
    compass = format_compass_message(prediction)
    if compass is not None:
        return compass
    return (prediction.text or "").strip()


def _today_for_profile(profile: Profile, today: date | None) -> date:
    if today is not None:
        return today
    return datetime.now(ZoneInfo(profile.timezone)).date()


async def _enqueue_pipeline(
    session: AsyncSession,
    user_id,
    target: date,
    prediction: Prediction | None,
) -> None:  # noqa: ANN001
    if prediction is None:
        await enqueue_prediction_pipeline(session, user_id, target)
        return
    await resume_prediction_pipeline(session, user_id, target, prediction)


async def request_today_prediction(
    session: AsyncSession,
    user: User,
    profile: Profile,
    today: date | None = None,
) -> PredictionRequestOutcome:
    """Запросить предсказание на день через RabbitMQ (без дублей при повторных нажатиях)."""
    target = _today_for_profile(profile, today)
    existing = await predictions_crud.get_prediction_for_date(session, user.id, target)

    if existing is not None:
        if existing.sent_at is not None or existing.status == PredictionStatus.SENT.value:
            return PredictionRequestOutcome(
                status=PredictionRequestStatus.READY,
                prediction=existing,
            )
        if await is_prediction_pending(user.id, target):
            return PredictionRequestOutcome(status=PredictionRequestStatus.IN_PROGRESS)
        if not await try_mark_prediction_pending(user.id, target):
            return PredictionRequestOutcome(status=PredictionRequestStatus.IN_PROGRESS)
        try:
            await _enqueue_pipeline(session, user.id, target, existing)
        except Exception:
            await clear_prediction_pending(user.id, target)
            raise
        return PredictionRequestOutcome(status=PredictionRequestStatus.QUEUED)

    if not await try_mark_prediction_pending(user.id, target):
        return PredictionRequestOutcome(status=PredictionRequestStatus.IN_PROGRESS)
    try:
        await _enqueue_pipeline(session, user.id, target, None)
    except Exception:
        await clear_prediction_pending(user.id, target)
        raise
    return PredictionRequestOutcome(status=PredictionRequestStatus.QUEUED)


async def get_or_create_today_prediction(
    session: AsyncSession,
    user: User,
    profile: Profile,
    today: date | None = None,
) -> Prediction | None:
    outcome = await request_today_prediction(session, user, profile, today)
    if outcome.status == PredictionRequestStatus.READY:
        return outcome.prediction
    return None


async def mark_prediction_sent(session: AsyncSession, prediction: Prediction) -> None:
    prediction.sent_at = datetime.now(timezone.utc)
    prediction.status = PredictionStatus.SENT.value
    await session.flush()
