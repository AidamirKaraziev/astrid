import asyncio
import logging

from aiogram import Bot, Dispatcher

logger = logging.getLogger(__name__)

POLLING_RESTART_DELAY_SECONDS = 5


async def prepare_bot_for_polling(bot: Bot) -> None:
    """Проверка токена и снятие webhook (иначе getUpdates молчит)."""
    me = await bot.get_me()
    logger.info(
        "Telegram bot authorized: @%s id=%d (%s)",
        me.username,
        me.id,
        me.full_name,
    )
    webhook = await bot.get_webhook_info()
    if webhook.url:
        logger.warning(
            "На боте был webhook %s — удаляем для polling",
            webhook.url,
        )
    await bot.delete_webhook(drop_pending_updates=False)


async def run_polling_supervisor(dp: Dispatcher, bot: Bot) -> None:
    """Polling с авторестартом: FastAPI не должен оставаться без бота молча."""
    while True:
        try:
            await prepare_bot_for_polling(bot)
            await dp.start_polling(
                bot,
                handle_signals=False,
                close_bot_session=False,
            )
            logger.warning(
                "Telegram polling завершился без ошибки, перезапуск через %ss",
                POLLING_RESTART_DELAY_SECONDS,
            )
        except asyncio.CancelledError:
            logger.info("Telegram polling остановлен (shutdown)")
            raise
        except Exception:
            logger.exception(
                "Telegram polling упал, перезапуск через %ss",
                POLLING_RESTART_DELAY_SECONDS,
            )
        await asyncio.sleep(POLLING_RESTART_DELAY_SECONDS)
