from datetime import datetime
from uuid import UUID

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from astra.places.getters import get_place_read
from astra.referrals import crud as referrals_crud
from astra.referrals.getters import get_referral_stats
from astra.services.prediction_service import get_or_create_today_prediction
from astra.services.referral_service import complete_referral_rewards
from astra.telegram.handlers.places import start_birth_place_step
from astra.telegram.keyboards import main_menu_keyboard, share_keyboard
from astra.telegram.states import OnboardingStates
from astra.telegram.utils import parse_birth_date
from astra.users import crud as users_crud

router = Router(name="onboarding")


@router.message(OnboardingStates.name)
async def onboarding_name(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    name = (message.text or "").strip() or data.get("default_name", "друг")
    await state.update_data(display_name=name)
    await state.set_state(OnboardingStates.birth_date)
    await message.answer(
        "📅 Укажи дату рождения в формате <b>ДД.ММ.ГГГГ</b>\n"
        "Например: <code>15.03.1990</code>",
        parse_mode="HTML",
    )


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

    prediction = await get_or_create_today_prediction(session, user, profile)
    await state.clear()

    stats = await get_referral_stats(session, user.id)
    share_url = (
        f"https://t.me/share/url?url={stats.referral_link}"
        f"&text={_url_encode('Моё предсказание от Astra ✨')}"
    )

    await message.answer(
        "🎉 Готово! Каждый день в 09:00 пришлю предсказание.\n\n" + prediction.text,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        "Твоё меню:",
        reply_markup=main_menu_keyboard(),
    )
    await message.answer(
        "Хочешь поделиться с подругой?",
        reply_markup=share_keyboard(share_url),
    )


def _url_encode(text: str) -> str:
    from urllib.parse import quote

    return quote(text)
