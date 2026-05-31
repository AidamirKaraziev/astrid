from datetime import datetime
from uuid import UUID

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from astra.places.getters import get_place_read
from astra.referrals import crud as referrals_crud
from astra.services.prediction_service import (
    format_prediction_for_user,
    get_or_create_today_prediction,
)
from astra.services.referral_service import complete_referral_rewards
from astra.telegram.handlers.places import start_birth_place_step
from astra.telegram.keyboards import main_menu_keyboard
from astra.telegram.states import OnboardingStates
from astra.telegram.utils import parse_birth_date
from astra.users import crud as users_crud

router = Router(name="onboarding")


@router.message(OnboardingStates.birth_date)
async def onboarding_birth_date(message: Message, state: FSMContext) -> None:
    parsed = parse_birth_date(message.text or "")
    if parsed is None:
        await message.answer("Не могу разобрать дату. Попробуй ещё раз: ДД.ММ.ГГГГ")
        return
    await state.update_data(birth_date=parsed.isoformat())
    await start_birth_place_step(message, state)


async def finish_onboarding(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    user_id = UUID(data["user_id"])
    user = await users_crud.get_user_by_id(session, user_id)
    if user is None:
        await message.answer("Что-то пошло не так. Нажми /start")
        return

    birth_place_id = UUID(data["birth_place_id"])
    notification_place_id = UUID(data["notification_place_id"])
    birth_place = data.get("birth_place_display", "")
    notification_display = data.get("notification_place_display", "")
    timezone = data.get("notification_timezone", "Europe/Moscow")

    notif_place = await get_place_read(session, notification_place_id)
    if notif_place:
        timezone = notif_place.timezone
        notification_display = notif_place.display_name

    birth_date = datetime.fromisoformat(data["birth_date"]).date()
    display_name = data["display_name"]

    if user.profile:
        profile = await users_crud.update_profile(
            session,
            user.profile,
            display_name=display_name,
            birth_date=birth_date,
            birth_place_id=birth_place_id,
            notification_place_id=notification_place_id,
            birth_place=birth_place,
            city=notification_display,
            timezone=timezone,
        )
    else:
        profile = await users_crud.create_profile(
            session,
            user_id=user.id,
            display_name=display_name,
            birth_date=birth_date,
            birth_place_id=birth_place_id,
            notification_place_id=notification_place_id,
            birth_place=birth_place,
            city=notification_display,
            timezone=timezone,
        )

    user.onboarding_completed = True
    await complete_referral_rewards(session, user)
    await referrals_crud.get_or_create_referral_code(session, user.id)

    await message.answer(
        "Поздравляю! Регистрация завершена ♥️\n\n"
        "Мы отправили тебе предсказание на день — подожди немного 🫂",
        reply_markup=ReplyKeyboardRemove(),
    )

    prediction = await get_or_create_today_prediction(session, user, profile)
    if prediction is not None:
        await message.answer(
            format_prediction_for_user(prediction, user, profile),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "Готовлю предсказание ✨ Пришлю через минуту — "
            "или нажми «🔮 Предсказание на сегодня».",
        )

    await state.clear()
    await message.answer("Твоё меню:", reply_markup=main_menu_keyboard())
