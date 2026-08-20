from aiogram import Router, F
from aiogram.types import CallbackQuery

import database as db
import keyboards as kb
from config import BOOK_NAME, BOOK_PRICE, PRIZE_TEXT

router = Router()


@router.callback_query(F.data == "join_contest")
async def cb_join_contest(callback: CallbackQuery):
    user = await db.get_user_by_tg_id(callback.from_user.id)
    if not user:
        await callback.answer("Avval ro'yxatdan o'ting: /start", show_alert=True)
        return
    if user["is_blocked"]:
        await callback.answer("Siz bloklangansiz.", show_alert=True)
        return

    if await db.is_participant(user["id"]):
        await callback.message.answer(
            "Siz allaqachon tanlov ishtirokchisisiz! Kitobingizni yuklab olishingiz mumkin 👇",
            reply_markup=kb.download_book_kb(),
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
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.payment_kb())
