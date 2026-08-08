"""Последний рубеж: сообщение, которое не подошло ни одному сценарию.

До сих пор такое сообщение не получало ничего. Молчание — худший из отказов:
человек не понимает, сломался бот или он сам сделал что-то не то, и уходит,
не пожаловавшись.

Попасть сюда можно тремя способами:

* состояние в Redis пережило деплой, а шага с таким именем больше нет —
  человек отвечает на вопрос, которого в новой версии не существует;
* человек пишет боту просто так, вне сценария;
* нажата кнопка из старого сообщения в истории чата — там callback, который
  давно ничего не значит, и без ответа Telegram крутит часики.

Роутер подключается последним, поэтому перехватить чужой сценарий не может:
до него доходит только то, что не забрал никто.
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.observability import Event, get_logger
from astra.telegram.keyboards import main_menu_keyboard
from astra.users import crud as users_crud

log = get_logger(__name__)

router = Router(name="fallback")

LOST_IN_ONBOARDING_TEXT = (
    "Кажется, мы не закончили знакомство ✨\n\nЖми /start — начнём заново."
)

LOST_IN_MENU_TEXT = "Кажется, мы прервались. Выбери, что дальше 👇"

UNKNOWN_COMMAND_TEXT = "Такой команды у меня нет. Открыть меню — /start"

STALE_BUTTON_TEXT = "Эта кнопка из старого сообщения — открой раздел заново"


@router.message(F.chat.type == "private")
async def unhandled_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Ответить хоть что-то и вернуть человека в понятное место."""
    stale_state = await state.get_state()
    if stale_state is not None:
        # Состояние есть, а обработчика для него нет — значит оно осталось от
        # прошлой версии бота. Держать человека в нём смысла нет.
        await state.clear()

    log.info(
        Event.TELEGRAM_MESSAGE_UNHANDLED,
        stale_state=stale_state,
        content_type=message.content_type,
    )

    if (message.text or "").startswith("/"):
        await message.answer(UNKNOWN_COMMAND_TEXT)
        return

    user = None
    if message.from_user is not None:
        user = await users_crud.get_user_by_telegram_id(session, message.from_user.id)

    if user is None or not user.onboarding_completed:
        await message.answer(LOST_IN_ONBOARDING_TEXT)
        return

    await message.answer(LOST_IN_MENU_TEXT, reply_markup=main_menu_keyboard())


@router.callback_query()
async def unhandled_callback(callback: CallbackQuery) -> None:
    """Кнопка, за которой уже ничего нет: без ответа Telegram крутит часики."""
    log.info(Event.TELEGRAM_CALLBACK_UNHANDLED, data=callback.data)
    await callback.answer(STALE_BUTTON_TEXT, show_alert=False)
