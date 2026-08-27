import asyncio
import logging
import inspect
import random
import datetime as dt
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

import database as db
from config import TZ_TASHKENT, TEST_DURATION_MINUTES, TOTAL_QUESTIONS
from utils.questions import load_questions
import keyboards as kb
from handlers.test import send_question, force_finish_user

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

        # DIQQAT: db.start_test() ichida started_at avtomatik va TO'G'RI turda
        # (epoch son — time.time()) saqlanadi. Oldin bu yerda alohida
        # db.create_or_reset_result(..., started_at=now.isoformat()) chaqirilar
        # edi — bu ISO matn edi, lekin test.py va pdf_generator.py buni SON
        # sifatida ishlatadi (masalan finished_at - started_at). Natijada
        # test vaqti tekshiruvi va PDF hisobot yaratish xato berardi.
        await db.start_test(user_id, order)

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
    """
    Barcha ishtirokchilarga test boshlanish xabarini yuboradi.

    DIQQAT — MUHIM O'ZGARISH: oldin bu funksiya ishtirokchilarga xabarni
    KETMA-KET (bittadan-bittaga) yuborardi. Ko'p ishtirokchi (masalan
    800 kishi) bo'lganda, bu oxirgi ishtirokchiga xabar yetib borishi
    BIRINCHI ishtirokchidan bir necha DAQIQA kech qolishiga sabab bo'lardi
    — bu adolatsizlik (kim oldin xabar olsa, testga tayyorlanish uchun
    ko'proq vaqtga ega bo'ladi).

    Endi xabarlar PARALLEL, lekin nazorat ostida (bir vaqtning o'zida
    ko'pi bilan MAX_CONCURRENT_SENDS tasi) yuboriladi — bu Telegram
    serverining "juda tez-tez xabar yubormang" cheklovini (rate limit)
    buzmagan holda, jarayonni sezilarli tezlashtiradi.
    """
    logger.info(">>> TEST BARCHA ISHTIROKCHILAR UCHUN BOSHLANMOQDA <<<")
    participants = await db.get_all_participants()
    questions = load_questions()

    if not questions:
        logger.error("Savollar bazasi bo'sh!")
        return

    if not participants:
        logger.warning("Bazada ishtirokchilar mavjud emas.")
        return

    MAX_CONCURRENT_SENDS = 20  # bir vaqtda ko'pi bilan shuncha xabar yuboriladi
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SENDS)

    async def _send_one(p):
        async with semaphore:
            try:
                user_id = p["user_id"] if "user_id" in p.keys() else p[1]
                user = await db.get_user_by_id(user_id)
                if not user or user["is_blocked"]:
                    return
                await _start_user_test_direct(bot, user["telegram_id"], user["id"], questions)
            except Exception as e:
                logger.error(f"Foydalanuvchiga test yuborishda xatolik: {e}")

    await asyncio.gather(*(_send_one(p) for p in participants))
    logger.info(f">>> {len(participants)} TA ISHTIROKCHIGA TEST BOSHLANISH XABARI YUBORILDI <<<")


async def _end_test_for_all(bot: Bot):
    """
    Test vaqti tugaganda hali ulgurmagan (in_progress) ishtirokchilarni
    majburiy yakunlaydi.

    DIQQAT: oldin bu yerda db.force_finish_all_active_tests() deb bitta
    "sehrli" DB funksiyasi chaqirilar edi — lekin bunday funksiya
    database.py da yo'q edi, VA muhimi, faqat bazani yangilash yetarli
    emas: har bir foydalanuvchiga o'z natija PDF fayli ham yuborilishi
    kerak. Buni faqat bot orqali (Telegram xabar/fayl yuborish) qilish
    mumkin, database.py buni bajara olmaydi. Shu sababli endi bu yerda
    test.py dagi force_finish_user() chaqirilib, har bir ulgurmagan
    foydalanuvchiga to'g'ri tarzda: natija hisoblanadi, bazaga yoziladi,
    VA shaxsiy PDF fayli ham yuboriladi.
    """
    logger.info(">>> TEST YAKUNLANDI (VAQT TUGADI) <<<")
    in_progress = await db.get_all_in_progress_tests()
    if not in_progress:
        logger.info("Vaqt tugaganda hech kim 'in_progress' holatida emas edi.")
        return

    for row in in_progress:
        try:
            await force_finish_user(bot, row["user_id"], row["telegram_id"])
        except Exception as e:
            logger.error(f"Majburiy yakunlashda xatolik (user_id={row['user_id']}): {e}")

    logger.info(f"{len(in_progress)} ta ishtirokchi majburiy yakunlandi.")


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