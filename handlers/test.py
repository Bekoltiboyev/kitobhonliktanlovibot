import os
import json
import random
import tempfile
import asyncio
import logging
import datetime as dt

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, FSInputFile

import database as db
import keyboards as kb
from utils.questions import load_questions, get_user_shuffled_options
from utils.pdf_generator import generate_user_result_pdf
from config import TEST_DURATION_MINUTES, TOTAL_QUESTIONS, NEGATIVE_MARK, TZ_TASHKENT

router = Router()
logger = logging.getLogger(__name__)

# DIQQAT: savollarni bot ishga tushganda bir marta xotiraga yuklab, keshlab qo'yish
# XATOLIKKA OLIB KELADI — admin Excel orqali yangi savollar yuklasa, bu kesh
# eskiligicha qolib ketadi va indekslar mos kelmay qolib botning javob
# bermay "qotib qolishiga" sabab bo'ladi. Shu sababli har joyda load_questions()
# to'g'ridan-to'g'ri (keshsiz) chaqiriladi.
#
# Variantlarni har bir user uchun aralashtirish mantig'i utils/questions.py
# ichidagi get_user_shuffled_options() da — chunki uni pdf_generator.py ham
# ishlatadi va ikkalasi bir xil natija berishi shart.


@router.callback_query(F.data == "time_left")
async def cb_time_left(callback: CallbackQuery):
    test_time_str = await db.get_setting("test_start_time")
    if not test_time_str:
        await callback.answer("Test vaqti hali e'lon qilinmagan.", show_alert=True)
        return

    test_time = dt.datetime.fromisoformat(test_time_str)

    # Agar bazadagi vaqtda timezone bo'lmasa, unga ham TZ_TASHKENT ulaymiz
    if test_time.tzinfo is None:
        test_time = test_time.replace(tzinfo=TZ_TASHKENT)

    now = dt.datetime.now(TZ_TASHKENT)

    if now >= test_time:
        await callback.answer("Test allaqachon boshlangan yoki yakunlangan!", show_alert=True)
        return

    delta = test_time - now
    days, rem = divmod(int(delta.total_seconds()), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    await callback.answer(
        f"Testgacha: {days} kun {hours} soat {minutes} daqiqa qoldi", show_alert=True
    )


async def begin_test_for_user(bot: Bot, user_id: int, telegram_id: int):
    existing = await db.get_test_result(user_id)
    if existing:
        return

    questions = load_questions()

    # Savollar hovuzidan (masalan 300-500 ta) har bir user uchun faqat
    # TOTAL_QUESTIONS (config.py, standart 60) tasi tasodifiy tanlanadi.
    sample_size = min(TOTAL_QUESTIONS, len(questions))
    order = random.sample(range(len(questions)), sample_size)

    await db.start_test(user_id, order)
    try:
        await bot.send_message(
            telegram_id,
            f"🚀 Test boshlandi! Sizda {TOTAL_QUESTIONS} ta savol va "
            f"{TEST_DURATION_MINUTES} daqiqa vaqt bor. Omad!",
        )
    except Exception:
        return
    await send_question(bot, telegram_id, user_id, 0)


async def send_question(bot: Bot, telegram_id: int, user_id: int, step_index: int):
    result = await db.get_test_result(user_id)
    if not result:
        return

    order = json.loads(result["question_order"])
    if step_index >= len(order):
        await finalize_user_test(bot, user_id, telegram_id)
        return

    questions = load_questions()

    # Foydalanuvchiga tegishli haqiqiy savol indeksi
    real_q_index = order[step_index]
    if real_q_index >= len(questions):
        # Savollar fayli test boshlanganidan keyin almashtirilgan va qisqarib qolgan bo'lishi mumkin.
        logger.error(
            f"Savol indeksi ({real_q_index}) joriy savollar ro'yxati uzunligidan ({len(questions)}) katta. "
            f"user_id={user_id}, step_index={step_index}. Test majburan yakunlanmoqda."
        )
        await finalize_user_test(bot, user_id, telegram_id)
        return

    q = questions[real_q_index]
    user_options, _ = get_user_shuffled_options(user_id, real_q_index, q)

    text = f"❓ <b>{step_index + 1}/{len(order)}-savol</b>\n\n{q['question']}"
    await bot.send_message(
        telegram_id, text, parse_mode="HTML",
        reply_markup=kb.question_kb(step_index, user_options),
        # protect_content=True — Telegram darajasida forward qilish va
        # "Copy" (nusxalash) tugmasini o'chiradi. Bu ekran suratini olishning
        # oldini ololmaydi, lekin savol matnini bir tugma bosib boshqa
        # do'stiga yuborib/nusxalab yuborishni sezilarli qiyinlashtiradi —
        # xuddi kitob fayli uchun ishlatilgan himoyaning o'zi.
        protect_content=True,
    )


@router.callback_query(F.data.startswith("ans_"))
async def cb_answer(callback: CallbackQuery, bot: Bot):
    try:
        _, step_index_str, choice = callback.data.split("_")
        step_index = int(step_index_str)

        user = await db.get_user_by_tg_id(callback.from_user.id)
        if not user:
            await callback.answer()
            return
        result = await db.get_test_result(user["id"])
        if not result or result["status"] != "in_progress":
            await callback.answer("Test faol emas.", show_alert=True)
            return
        if result["current_index"] != step_index:
            logger.warning(
                f"[DIAGNOSTIKA] Mos kelmadi -> tugmadagi step_index={step_index}, "
                f"bazadagi current_index={result['current_index']}, "
                f"user_id={user['id']}, tg_id={callback.from_user.id}, "
                f"test_status={result['status']}, started_at={result['started_at']}"
            )
            await callback.answer("Bu savol allaqachon javoblangan.", show_alert=True)
            return

        started = dt.datetime.fromtimestamp(result["started_at"])
        if dt.datetime.now() > started + dt.timedelta(minutes=TEST_DURATION_MINUTES):
            await finalize_user_test(bot, user["id"], callback.from_user.id)
            await callback.answer("Test vaqti tugadi.", show_alert=True)
            return

        # Haqiqiy savol indeksiga javobni bog'laymiz
        order = json.loads(result["question_order"])
        real_q_index = order[step_index]

        # Savollar ro'yxatidan haqiqiy savolni olib, to'g'ri javobga tekshiramiz
        questions = load_questions()
        if real_q_index >= len(questions):
            logger.error(
                f"Savol indeksi ({real_q_index}) joriy savollar ro'yxati uzunligidan ({len(questions)}) katta. "
                f"user_id={user['id']}. Test majburan yakunlanmoqda."
            )
            await finalize_user_test(bot, user["id"], callback.from_user.id)
            await callback.answer("Savollar ro'yxati yangilangan, test yakunlandi.", show_alert=True)
            return

        current_q = questions[real_q_index]
        _, user_correct = get_user_shuffled_options(user["id"], real_q_index, current_q)
        is_correct = (choice == user_correct)

        await db.save_answer(user["id"], real_q_index, choice, step_index + 1, is_correct)

        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

        await callback.answer(f"Javobingiz qabul qilindi: {choice}")
        await send_question(bot, callback.from_user.id, user["id"], step_index + 1)
    except Exception as e:
        logger.error(f"cb_answer da xatolik: {e}", exc_info=True)
        try:
            await callback.answer("Xatolik yuz berdi, qaytadan urinib ko'ring.", show_alert=True)
        except Exception:
            pass


async def _compute_score(user_id: int, answers: dict, questions: list):
    correct = wrong = 0
    for i, q in enumerate(questions):
        given = answers.get(str(i))
        if given is None:
            continue
        _, user_correct = get_user_shuffled_options(user_id, i, q)
        if given == user_correct:
            correct += 1
        else:
            wrong += 1
    unanswered = len(questions) - correct - wrong
    score = correct - wrong * NEGATIVE_MARK
    return correct, wrong, unanswered, score


async def finalize_user_test(bot: Bot, user_id: int, telegram_id: int):
    result = await db.get_test_result(user_id)
    if not result or result["status"] == "finished":
        return

    questions = load_questions()
    answers = json.loads(result["answers_json"]) if result["answers_json"] else {}
    correct, wrong, unanswered, score = await _compute_score(user_id, answers, questions)
    await db.finish_test(user_id, correct, wrong, unanswered, score)

    user = await db.get_user_by_id(user_id)
    result = await db.get_test_result(user_id)

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f"natija_{telegram_id}.pdf")
        await asyncio.to_thread(
            generate_user_result_pdf,
            path,
            user=dict(user),
            result={
                "started_at": result["started_at"],
                "finished_at": result["finished_at"],
                "correct_count": correct,
                "wrong_count": wrong,
                "unanswered_count": unanswered,
                "score": score,
                "answers": answers,
            },
            questions=questions,
            user_id=user_id,
        )
        try:
            await bot.send_document(
                telegram_id, FSInputFile(path),
                caption="✅ Test yakunlandi! Natijangiz ilova qilingan hisobotda.",
                # Natija hisobotida to'g'ri javoblar ham ko'rinadi — bu ham
                # tarqatilmasligi uchun himoyalanadi.
                protect_content=True,
            )
        except Exception:
            pass


async def force_finish_user(bot: Bot, user_id: int, telegram_id: int):
    await finalize_user_test(bot, user_id, telegram_id)


@router.message(Command("finish_test"))
async def cmd_manual_finish(message: Message, bot: Bot):
    user = await db.get_user_by_tg_id(message.from_user.id)
    if not user:
        return
    result = await db.get_test_result(user["id"])
    if not result or result["status"] != "in_progress":
        await message.answer("Sizda faol test yo'q.")
        return
    await finalize_user_test(bot, user["id"], message.from_user.id)