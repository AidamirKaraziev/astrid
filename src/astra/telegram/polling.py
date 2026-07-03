import asyncio

from aiogram import Bot, Dispatcher

from astra.core.observability import Event, get_logger

log = get_logger(__name__)

POLLING_RESTART_DELAY_SECONDS = 5


async def prepare_bot_for_polling(bot: Bot) -> None:
    """Проверка токена и снятие webhook (иначе getUpdates молчит)."""
    me = await bot.get_me()
    log.info(
        Event.TELEGRAM_POLLING_STARTED,
        bot_username=me.username,
        bot_id=me.id,
        bot_name=me.full_name,
    )
    webhook = await bot.get_webhook_info()
    if webhook.url:
        log.warning(
            Event.TELEGRAM_POLLING_STARTED,
            action="webhook_removed",
            webhook_url=webhook.url,
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
            log.warning(
                Event.TELEGRAM_POLLING_ERROR,
                reason="stopped_without_error",
                restart_delay_sec=POLLING_RESTART_DELAY_SECONDS,
            )
        except asyncio.CancelledError:
            log.info(Event.TELEGRAM_POLLING_STOPPED, reason="shutdown")
            raise
        except Exception:
            log.exception(
                Event.TELEGRAM_POLLING_ERROR,
                restart_delay_sec=POLLING_RESTART_DELAY_SECONDS,
            )
        await asyncio.sleep(POLLING_RESTART_DELAY_SECONDS)
