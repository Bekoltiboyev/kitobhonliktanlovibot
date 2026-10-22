import asyncio
import logging
import inspect
import random
import datetime as dt
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger

import database as db
from config import TZ_TASHKENT, TEST_DURATION_MINUTES, TOTAL_QUESTIONS, ADMIN_IDS, PER_USER_SHUFFLE
from utils.questions import load_questions
from utils.telegram_safe import safe_send_message
import keyboards as kb
from handlers.test import send_question, force_finish_user

logger = logging.getLogger(__name__)

TEST_START_JOB_ID = "test_start"
TEST_END_JOB_ID = "test_end"
REMINDER_JOB_ID = "daily_reminder"
REMINDER_HOUR = 10  # har kuni soat 10:00 (Toshkent vaqti)

_UZ_MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul",
              "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]


def _reminder_text(test_time: dt.datetime, today: dt.date) -> str:
    days = (test_time.date() - today).days
    date_s = f"{test_time.day}-{_UZ_MONTHS[test_time.month - 1]}, soat {test_time:%H:%M}"
    if days <= 0:
        head = f"🔔 <b>Bugun test kuni!</b>\nTest bugun soat <b>{test_time:%H:%M}</b> da boshlanadi."
        tail = "Vaqtida botda bo'ling, internetingiz va telefoningiz zaryadini tekshirib qo'ying. Omad! 🍀"
    elif days == 1:
        head = f"🔔 <b>Test ertaga!</b>\nSana: <b>{date_s}</b>."
        tail = "Kitobni yana bir bor ko'zdan kechirib, yaxshi dam oling. Omad! 🍀"
    else:
        head = f"🔔 <b>Eslatma: testgacha {days} kun qoldi.</b>\nSana: <b>{date_s}</b>."
        tail = "Kitobni o'qib, tayyorgarlikni davom ettiring. Test shu bot orqali o'tkaziladi."
    return f"{head}\n\n{tail}"


async def _daily_reminder(bot: Bot):
    """Har kuni faqat TO'LOV QILGANLARGA test haqida eslatma yuboradi (test kunigacha)."""
    try:
        saved = await db.get_setting("test_start_time")
        if not saved:
            return
        test_time = dt.datetime.fromisoformat(saved)
        if test_time.tzinfo is None:
            test_time = test_time.replace(tzinfo=TZ_TASHKENT)
        now = dt.datetime.now(TZ_TASHKENT)
        if test_time <= now:
            return  # test boshlangan/o'tgan — eslatma kerak emas
        today = now.date()
        if await db.get_setting("reminder_last_date") == today.isoformat():
            return  # bugun allaqachon yuborilgan (qayta ishga tushganda takror ketmasin)
        await db.set_setting("reminder_last_date", today.isoformat())

        recipients = await db.get_broadcast_recipients(only_paid=True)
        text = _reminder_text(test_time, today)
        ok = fail = 0
        for i in range(0, len(recipients), 25):
            t0 = asyncio.get_event_loop().time()
            res = await asyncio.gather(
                *(safe_send_message(bot, tg, text, parse_mode="HTML") for tg in recipients[i:i + 25])
            )
            ok += sum(1 for r in res if r)
            fail += sum(1 for r in res if not r)
            spent = asyncio.get_event_loop().time() - t0
            if spent < 1.0:
                await asyncio.sleep(1.0 - spent)
        logger.info(f"Kunlik eslatma: {ok} yetkazildi, {fail} yetmadi (jami {len(recipients)})")
        for admin_id in ADMIN_IDS:
            await safe_send_message(
                bot, admin_id,
                f"🔔 Kunlik eslatma yuborildi (faqat to'lov qilganlarga)\n"
                f"✅ Yetkazildi: {ok}\n⚠️ Yetmadi (bloklagan va h.k.): {fail}\nJami: {len(recipients)}",
            )
    except Exception as e:
        logger.error(f"Kunlik eslatmada xatolik: {e}")


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
        order = (random.sample(range(total_q), sample_size) if PER_USER_SHUFFLE
                 else list(range(sample_size)))

        # DIQQAT: db.start_test() ichida started_at avtomatik va TO'G'RI turda
        # (epoch son — time.time()) saqlanadi. Oldin bu yerda alohida
        # db.create_or_reset_result(..., started_at=now.isoformat()) chaqirilar
        # edi — bu ISO matn edi, lekin test.py va pdf_generator.py buni SON
        # sifatida ishlatadi (masalan finished_at - started_at). Natijada
        # test vaqti tekshiruvi va PDF hisobot yaratish xato berardi.
        await db.start_test(user_id, order)

        # BITTA xabar: "test boshlandi" sarlavhasi + 1-savol birga yuboriladi.
        # Ilgari ikkita alohida xabar ketardi (yuzlab odamda yuborish 2 baravar
        # sekin bo'lardi, oxirgi odam ancha kech olardi).
        prefix = (
            "🏁 <b>DIQQAT, TEST BOSHLANDI!</b>\n"
            f"⏱ <b>Vaqtingiz:</b> {TEST_DURATION_MINUTES} daqiqa\n\n"
        )
        sent = await send_question(bot, tg_id, user_id, 0, prefix=prefix)
        if sent is None:
            # Xabar yetkazib bo'lmadi (bloklagan/flood control tugadi) - shovqinli
            # xato o'rniga shu yerda to'xtaymiz.
            return
        # Vaqt hisobi savol HAQIQATAN yetib borgan paytdan boshlanadi (adolat).
        await db.reset_started_at(user_id)
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

    # Yuzlab ishtirokchi bo'lsa, ketma-ket yakunlash (har biriga PDF yasash + yuborish)
    # bir necha daqiqa olardi. Endi nazorat ostida parallel: bir vaqtda ko'pi bilan 10 ta.
    semaphore = asyncio.Semaphore(10)

    async def _finish_one(row):
        async with semaphore:
            try:
                await force_finish_user(bot, row["user_id"], row["telegram_id"])
            except Exception as e:
                logger.error(f"Majburiy yakunlashda xatolik (user_id={row['user_id']}): {e}")

    await asyncio.gather(*(_finish_one(row) for row in in_progress))

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

    scheduler.add_job(
        _daily_reminder,
        CronTrigger(hour=REMINDER_HOUR, minute=0, timezone=TZ_TASHKENT),
        args=[bot],
        id=REMINDER_JOB_ID,
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )

    saved_time_str = await db.get_setting("test_start_time")
    if saved_time_str:
        try:
            test_time = dt.datetime.fromisoformat(saved_time_str)
            if test_time.tzinfo is None:
                test_time = test_time.replace(tzinfo=TZ_TASHKENT)
            now = dt.datetime.now(TZ_TASHKENT)
            if test_time > now:
                await reschedule_test_jobs(scheduler, bot, test_time)
                logger.info(f"Rejalashtirilgan test vaqti yuklandi: {test_time}")
            else:
                # Bot test BOSHLANGANIDAN KEYIN qayta ishga tushgan (deploy, server
                # qayta yuklanishi...). Ilgari tugatish vazifasi yo'qolib, javob
                # bermay qolganlar hech qachon avtomatik yakunlanmasdi va natija
                # PDF sini olmasdi. Endi tugatish vazifasi qayta o'rnatiladi
                # (vaqti allaqachon o'tgan bo'lsa — darrov, bir marta ishga tushadi).
                end_time = test_time + dt.timedelta(minutes=TEST_DURATION_MINUTES, seconds=60)
                run_at = end_time if end_time > now else now + dt.timedelta(seconds=10)
                scheduler.add_job(
                    _end_test_for_all,
                    DateTrigger(run_date=run_at, timezone=TZ_TASHKENT),
                    args=[bot],
                    id=TEST_END_JOB_ID,
                    replace_existing=True,
                    misfire_grace_time=3600,
                )
                logger.info(f"Test allaqachon boshlangan: tugatish vazifasi {run_at} ga qayta o'rnatildi")
        except Exception as e:
            logger.error(f"Scheduler yuklashda xatolik: {e}")

    return scheduler