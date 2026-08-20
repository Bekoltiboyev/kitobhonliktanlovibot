import asyncio
import logging
import datetime as dt


from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import database as db
from config import BOT_TOKEN, TZ_TASHKENT
from handlers import registration, contest, payment, admin, test, leaderboard
from utils.scheduler import setup_scheduler, reschedule_test_jobs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    await db.init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # scheduler ni barcha handlerlarga aiogram DI orqali uzatamiz (masalan /settesttime uchun)
    scheduler = await setup_scheduler(bot)
    dp["scheduler"] = scheduler

    # Agar bot qayta ishga tushsa, avval o'rnatilgan test vaqtini qayta rejalashtiramiz
    saved_time = await db.get_setting("test_start_time")
    if saved_time:
        test_time = dt.datetime.fromisoformat(saved_time)
        if test_time.tzinfo is None:
            test_time = test_time.replace(tzinfo=TZ_TASHKENT)

        if test_time > dt.datetime.now(TZ_TASHKENT):
            await reschedule_test_jobs(scheduler, bot, test_time)

    dp.include_router(registration.router)
    dp.include_router(contest.router)
    dp.include_router(payment.router)
    dp.include_router(admin.router)
    dp.include_router(test.router)
    dp.include_router(leaderboard.router)

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot ishga tushdi...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
