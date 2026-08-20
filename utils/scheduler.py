import logging
import inspect
import json
import random
import datetime as dt
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

import database as db
from config import TZ_TASHKENT, TEST_DURATION_MINUTES, TOTAL_QUESTIONS
from utils.questions import load_questions
import keyboards as kb
from handlers.test import send_question

logger = logging.getLogger(__name__)

TEST_START_JOB_ID = "test_start"
TEST_END_JOB_ID = "test_end"


async def _start_user_test_direct(bot: Bot, tg_id: int, user_id: int, questions: list):
    """Har bir foydalanuvchi uchun testni noldan generatsiya qilib boshlab berish.

    Diqqat: birinchi savol test.py dagi send_question() orqali yuboriladi —
    shu bilan callback_data doim step_index (0,1,2...) asosida bo'ladi va
    test.py dagi cb_answer() bilan current_index solishtirishga mos keladi.
    Bu yerda o'zimiz alohida xabar yuborsak, savol tugmasidagi indeks bilan
    bazadagi current_index mos kelmay qolib, birinchi javob "allaqachon
    javoblangan" deb noto'g'ri rad etilardi.
    """
    try:
        total_q = len(questions)
        # Savollar hovuzi (masalan 300-500 ta) dan har bir user uchun
        # faqat TOTAL_QUESTIONS (config.py dagi, standart 60) tasi tasodifiy tanlanadi.
        # random.sample takrorlanmaydigan, tasodifiy tartibda tanlaydi - shu bilan
        # bir vaqtning o'zida ham savol soni cheklanadi, ham tartibi aralashtiriladi.
        sample_size = min(TOTAL_QUESTIONS, total_q)
        order = random.sample(range(total_q), sample_size)

        now = dt.datetime.now(TZ_TASHKENT)
        await db.create_or_reset_result(
            user_id=user_id,
            question_order=order,
            started_at=now.isoformat()
        )

        await bot.send_message(
            chat_id=tg_id,
            text=(
                "🏁 <b>DIQQAT, TEST BOSHLANDI!</b>\n"
                f"⏱ <b>Vaqtingiz:</b> {TEST_DURATION_MINUTES} daqiqa"
            ),
            parse_mode="HTML"
        )

        await send_question(bot, tg_id, user_id, 0)
    except Exception as e:
        logger.error(f"Foydalanuvchi {tg_id} ga test yuborishda xatolik: {e}")


async def _start_test_for_all(bot: Bot):
    logger.info(">>> TEST BARCHA ISHTIROKCHILAR UCHUN BOSHLANMOQDA <<<")
    participants = await db.get_all_participants()
    questions = load_questions()

    if not questions:
        logger.error("Savollar bazasi bo'sh!")
        return

    if not participants:
        logger.warning("Bazada ishtirokchilar mavjud emas.")
        return

    for p in participants:
        try:
            user_id = p["user_id"] if "user_id" in p.keys() else p[1]

            user = await db.get_user_by_id(user_id)
            if not user:
                continue

            if user["is_blocked"]:
                continue

            tg_id = user["telegram_id"]
            u_id = user["id"]

            await _start_user_test_direct(bot, tg_id, u_id, questions)

        except Exception as e:
            logger.error(f"Foydalanuvchiga test yuborishda xatolik: {e}")


async def _end_test_for_all(bot: Bot):
    logger.info(">>> TEST YAKUNLANDI (VAQT TUGADI) <<<")
    await db.force_finish_all_active_tests()


async def reschedule_test_jobs(scheduler: AsyncIOScheduler, bot: Bot, test_time: dt.datetime):
    # Agar adashib coroutine kelsa, uni await qilib oladi
    if inspect.iscoroutine(scheduler):
        scheduler = await scheduler

    if scheduler.get_job(TEST_START_JOB_ID):
        scheduler.remove_job(TEST_START_JOB_ID)
    if scheduler.get_job(TEST_END_JOB_ID):
        scheduler.remove_job(TEST_END_JOB_ID)

    scheduler.add_job(
        _start_test_for_all,
        DateTrigger(run_date=test_time, timezone=TZ_TASHKENT),
        args=[bot],
        id=TEST_START_JOB_ID,
        replace_existing=True,
        misfire_grace_time=3600
    )

    end_time = test_time + dt.timedelta(minutes=TEST_DURATION_MINUTES, seconds=60)
    scheduler.add_job(
        _end_test_for_all,
        DateTrigger(run_date=end_time, timezone=TZ_TASHKENT),
        args=[bot],
        id=TEST_END_JOB_ID,
        replace_existing=True,
        misfire_grace_time=3600
    )


async def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Bot ishga tushganda bazadagi saqlangan vaqt bo'yicha rejalashtirgichni yoqish."""
    scheduler = AsyncIOScheduler(timezone=TZ_TASHKENT)
    scheduler.start()

    saved_time_str = await db.get_setting("test_start_time")
    if saved_time_str:
        try:
            test_time = dt.datetime.fromisoformat(saved_time_str)
            now = dt.datetime.now(TZ_TASHKENT)
            if test_time > now:
                await reschedule_test_jobs(scheduler, bot, test_time)
                logger.info(f"Rejalashtirilgan test vaqti yuklandi: {test_time}")
        except Exception as e:
            logger.error(f"Scheduler yuklashda xatolik: {e}")

    return scheduler