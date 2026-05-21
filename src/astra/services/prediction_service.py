from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from astra.predictions import crud as predictions_crud
from astra.predictions.models import Prediction
from astra.services.astro_service import generate_daily_prediction
from astra.users.getters import calculate_profile_accuracy
from astra.users.models import Profile, User


def _zodiac_sign_from_profile(profile: Profile) -> str:
    d = (profile.birth_date.month, profile.birth_date.day)
    signs = [
        ((3, 21), (4, 19), "Овен"),
        ((4, 20), (5, 20), "Телец"),
        ((5, 21), (6, 20), "Близнецы"),
        ((6, 21), (7, 22), "Рак"),
        ((7, 23), (8, 22), "Лев"),
        ((8, 23), (9, 22), "Дева"),
        ((9, 23), (10, 22), "Весы"),
        ((10, 23), (11, 21), "Скорпион"),
        ((11, 22), (12, 21), "Стрелец"),
        ((12, 22), (1, 19), "Козерог"),
        ((1, 20), (2, 18), "Водолей"),
        ((2, 19), (3, 20), "Рыбы"),
    ]
    for start, end, name in signs:
        if start <= d <= end:
            return name
    return "Козерог"


def format_prediction_message(
    profile: Profile,
    body: str,
    *,
    points: int,
    streak: int,
) -> str:
    accuracy, hint = calculate_profile_accuracy(profile)
    sign = _zodiac_sign_from_profile(profile)
    inaccuracy = 100 - accuracy

    return (
        f"✨ <b>{profile.display_name}</b>, твоё предсказание на сегодня\n\n"
        f"☀️ Знак: <b>{sign}</b>\n\n"
        f"{body}\n\n"
        f"📊 Точность: <b>{accuracy}%</b>\n"
        f"<i>Неточность: {inaccuracy}%. {hint}</i>\n\n"
        f"🔥 Серия: <b>{streak}</b> дн. | ⭐ Баллы: <b>{points}</b>"
    )


def format_prediction_for_user(
    prediction: Prediction,
    user: User,
    profile: Profile,
) -> str:
    return format_prediction_message(
        profile,
        prediction.text,
        points=user.points,
        streak=user.streak_current,
    )


async def get_or_create_today_prediction(
    session: AsyncSession,
    user: User,
    profile: Profile,
    today: date | None = None,
    *,
    allow_async: bool = False,
) -> Prediction | None:
    from astra.core.config import get_settings
    from astra.messaging.publisher import publish_prediction_generate

    target = today or date.today()
    existing = await predictions_crud.get_prediction_for_date(session, user.id, target)
    if existing:
        return existing

    settings = get_settings()
    if allow_async and settings.rabbitmq_enabled:
        await publish_prediction_generate(user.id, target)
        return None

    return await generate_daily_prediction(session, user, profile, target=target)


async def mark_prediction_sent(session: AsyncSession, prediction: Prediction) -> None:
    prediction.sent_at = datetime.now(timezone.utc)
    await session.flush()
