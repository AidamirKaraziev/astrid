import random
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from astra.predictions import crud as predictions_crud
from astra.predictions.models import Prediction
from astra.users.getters import calculate_profile_accuracy
from astra.users.models import Profile, User

_STUB_BODIES = [
    "Сегодня звёзды советуют довериться интуиции — важный знак уже рядом.",
    "День благоприятен для мягких перемен. Не бойся сделать маленький шаг вперёд.",
    "Энергия дня поддерживает заботу о себе. Позволь себе отдых без чувства вины.",
    "В отношениях прислушайся к тишине — в ней больше ответов, чем кажется.",
    "Финансовый поток требует терпения: не спеши с решениями до вечера.",
    "Творческая искра особенно ярка — запиши мысль, которая придёт неожиданно.",
]


def _zodiac_sign(birth_date: date) -> str:
    d = (birth_date.month, birth_date.day)
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


def generate_prediction_body() -> str:
    return random.choice(_STUB_BODIES)


def format_prediction_message(
    profile: Profile,
    body: str,
    *,
    points: int,
    streak: int,
) -> str:
    accuracy, hint = calculate_profile_accuracy(profile)
    sign = _zodiac_sign(profile.birth_date)
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
) -> Prediction:
    target = today or date.today()
    existing = await predictions_crud.get_prediction_for_date(session, user.id, target)
    if existing:
        return existing

    body = generate_prediction_body()
    return await predictions_crud.create_prediction(
        session,
        user_id=user.id,
        prediction_date=target,
        text=body,
    )


async def mark_prediction_sent(session: AsyncSession, prediction: Prediction) -> None:
    prediction.sent_at = datetime.now(timezone.utc)
    await session.flush()
