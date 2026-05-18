from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.referrals import crud as referrals_crud
from astra.services.points_service import register_daily_activity
from astra.services.referral_service import apply_referral_on_start
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from astra.telegram.keyboards import main_menu_keyboard
from astra.telegram.states import OnboardingStates
from astra.telegram.utils import default_display_name, extract_referral_code
from astra.users import crud as users_crud

router = Router(name="start")


@router.message(Command("start"))
async def cmd_start(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.from_user is None:
        return

    tg = message.from_user
    user = await users_crud.get_user_by_telegram_id(session, tg.id)
    if user is None:
        user = await users_crud.create_user(
            session,
            telegram_id=tg.id,
            username=tg.username,
            language_code=tg.language_code,
        )
        ref_code = extract_referral_code(command.args)
        if ref_code:
            await apply_referral_on_start(session, user, ref_code)

    await register_daily_activity(session, user)
    await state.clear()

    restart = (command.args or "").strip().lower() in {"restart", "again", "reset", "заново"}
    if user.onboarding_completed and user.profile and not restart:
        await message.answer(
            f"С возвращением, {user.profile.display_name}! ✨\n"
            "Твоё меню внизу — выбирай действие.\n\n"
            "Чтобы пройти регистрацию заново: <code>/start restart</code>",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return

    if restart:
        user.onboarding_completed = False

    await state.set_state(OnboardingStates.welcome)
    await state.update_data(
        default_name=default_display_name(tg),
        user_id=str(user.id),
    )
    begin_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="▶️ Начать")]],
        resize_keyboard=True,
    )
    await message.answer(
        "✨ <b>Добро пожаловать в Astra</b>\n\n"
        "Магическая поддержка каждый день — мягко, без навязчивости.\n"
        "Персональные предсказания, которые помогают лучше чувствовать свой путь.",
        parse_mode="HTML",
        reply_markup=begin_kb,
    )


@router.message(F.text == "▶️ Начать")
@router.message(Command("continue"))
async def cmd_continue(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current != OnboardingStates.welcome.state:
        return
    data = await state.get_data()
    default_name = data.get("default_name", "друг")
    await state.set_state(OnboardingStates.name)
    await message.answer(
        f"Как тебя называть?\n"
        f"Сейчас: <b>{default_name}</b>\n\n"
        "Отправь имя или нажми Enter — оставим как есть (отправь то же имя).",
        parse_mode="HTML",
    )
