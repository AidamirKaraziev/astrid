from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import get_settings
from astra.referrals import crud as referrals_crud
from astra.services.onboarding_service import sync_user_from_telegram
from astra.services.points_service import register_daily_activity
from astra.services.referral_service import apply_referral_on_start
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from astra.telegram.button_texts import BTN_PROFILE
from astra.telegram.keyboards import main_menu_keyboard
from astra.telegram.keyboards import gender_keyboard
from astra.telegram.profile_gender_prompt import prompt_gender_if_missing
from astra.telegram.states import OnboardingStates
from astra.telegram.utils import (
    clean_display_name,
    default_display_name,
    extract_referral_code,
)
from astra.users import crud as users_crud

router = Router(name="start")

WELCOME_VIDEO_PATH = Path(__file__).resolve().parent.parent / "static" / "welcome.mp4"

# Первый экран: под видео с живым лицом говорить голосом сервиса нельзя, поэтому
# здоровается сама Астрид и сразу задаёт единственный вопрос. Обещание «без
# туманных пророчеств» здесь не украшение: люди приходят за поддержкой, но
# стесняются «гороскопчиков», и это снимает возражение до того, как оно
# возникнет. Три пункта вынесены в столбик с жирными зачинами: первый экран
# читают вертикально, по выделенным словам, а не построчно.
WELCOME_TEXT = (
    "✨ Привет! Я <b>Астрид</b> — твой астролог.\n\n"
    "Каждый день смотрю, что происходит в небе, и рассказываю по-человечески:\n\n"
    "💫 <b>Где попутный ветер</b>\n"
    "за что сегодня стоит взяться\n\n"
    "🌀 <b>Где лучше притормозить</b>\n"
    "что спокойно подождёт до завтра\n\n"
    "💜 <b>Без туманных пророчеств</b>\n"
    "живым языком, а не «гороскопчик»\n\n"
    "<b>Давай знакомиться — как мне к тебе обращаться?</b>"
)


def call_me_button_text(default_name: str) -> str:
    """Кнопка подставляет имя из Telegram: ответить можно одним касанием."""
    return f"Зови меня {default_name}"
_WELCOME_VIDEO_FILE_ID_KEY = "astra:telegram:welcome_video_file_id"


async def _get_cached_welcome_video_file_id() -> str | None:
    client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        return await client.get(_WELCOME_VIDEO_FILE_ID_KEY)
    finally:
        await client.aclose()


async def _cache_welcome_video_file_id(file_id: str) -> None:
    client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        await client.set(_WELCOME_VIDEO_FILE_ID_KEY, file_id)
    finally:
        await client.aclose()


@router.message(Command("start", "menu"))
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
    is_new_user = user is None
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
    else:
        await sync_user_from_telegram(
            session,
            user,
            username=tg.username,
            language_code=tg.language_code,
        )
        # Пользователь вернулся после блокировки бота — включаем рассылки обратно.
        await users_crud.clear_bot_blocked(session, user)

    await register_daily_activity(session, user)
    await state.clear()

    restart = (command.args or "").strip().lower() in {"restart", "again", "reset", "заново"}
    if user.onboarding_completed and user.profile and not restart:
        await message.answer("Главное меню ✨", reply_markup=main_menu_keyboard())
        await prompt_gender_if_missing(message, user.profile)
        return

    if restart:
        user.onboarding_completed = False

    await state.set_state(OnboardingStates.welcome)
    await state.update_data(
        default_name=default_display_name(tg),
        user_id=str(user.id),
    )

    default_name = default_display_name(tg)
    begin_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=call_me_button_text(default_name))]],
        resize_keyboard=True,
    )
    welcome_text = WELCOME_TEXT
    if is_new_user and WELCOME_VIDEO_PATH.exists():
        cached_file_id = await _get_cached_welcome_video_file_id()
        video = cached_file_id or FSInputFile(WELCOME_VIDEO_PATH)
        sent = await message.answer_video(
            video,
            caption=welcome_text,
            parse_mode="HTML",
            reply_markup=begin_kb,
        )
        if not cached_file_id and sent.video is not None:
            await _cache_welcome_video_file_id(sent.video.file_id)
    else:
        await message.answer(
            welcome_text,
            parse_mode="HTML",
            reply_markup=begin_kb,
        )


@router.message(OnboardingStates.welcome)
@router.message(Command("continue"))
async def onboarding_name(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Как обращаться: кнопка с именем из Telegram или своё, написанное текстом.

    Приветствие и вопрос об имени живут на одном экране, поэтому здесь ловится
    любое сообщение: нажатие кнопки — это тоже текст, просто заранее известный.
    Отдельного шага «тап, чтобы продолжить» больше нет — нажатие сразу что-то
    значит.
    """
    current = await state.get_state()
    if current != OnboardingStates.welcome.state:
        return
    data = await state.get_data()
    if not data.get("user_id") and message.from_user is not None:
        user = await users_crud.get_user_by_telegram_id(session, message.from_user.id)
        if user is not None:
            await state.update_data(user_id=str(user.id))

    default_name = str(data.get("default_name") or "друг")
    text = (message.text or "").strip()
    if text == call_me_button_text(default_name):
        display_name = default_name
    else:
        display_name = clean_display_name(text) or default_name

    await state.update_data(display_name=display_name)
    await state.set_state(OnboardingStates.gender)
    await message.answer(
        f"Рада знакомству, <b>{display_name}</b> ✨\n"
        f"Если что — имя можно поменять в разделе «{BTN_PROFILE}».\n\n"
        "И последнее: укажи свой пол — от него зависят формулировки в разборах.",
        parse_mode="HTML",
        reply_markup=gender_keyboard(),
    )
