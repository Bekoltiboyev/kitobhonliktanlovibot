from aiogram import Router, F
from aiogram.types import Message

import database as db
import keyboards as kb
from config import BOOK_NAME, BOOK_PRICE, PRIZE_TEXT

router = Router()


@router.message(F.text == "🎯 Tanlovda ishtirok etish")
async def cb_join_contest(message: Message):
    user = await db.get_user_by_tg_id(message.from_user.id)
    if not user:
        await message.answer("Avval ro'yxatdan o'ting: /start")
        return
    if user["is_blocked"]:
        await message.answer("Siz bloklangansiz.")
        return

    if await db.is_participant(user["id"]):
        await message.answer(
            "Siz allaqachon tanlov ishtirokchisisiz! Kitobingizni yuklab olishingiz mumkin 👇",
            reply_markup=kb.post_approval_kb(),
        )
        return

    text = (
        f"📚 <b>Tanlovga xush kelibsiz!</b>\n\n"
        f"📚 <b>Tanlov kitobi:</b> {BOOK_NAME}\n"
        f"💵 <b>ishtirok narxi:</b> {BOOK_PRICE}\n\n"
         "Tanlovda ishtirok etish uchun ishtirok shartlarini bajarish talab etiladi. "
        "Kitobni yuklab olganingizdan so'ng testda qatnashish imkoniyatiga ega bo'lasiz.\n\n"
        f"{PRIZE_TEXT}\n"
        "ℹ️ Batafsil ma'lumot va ishtirok shartlari keyingi bosqichda ko'rsatiladi. Kitobni ushbu botdan yuklab olmagan "
        "shaxsga tanlovda ishtirok etish imkoni berilmaydi."
    )
    await message.answer(text, parse_mode="HTML", reply_markup=kb.payment_kb())