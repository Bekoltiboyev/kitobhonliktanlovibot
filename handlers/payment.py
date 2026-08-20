import os
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.fsm.context import FSMContext

import database as db
import keyboards as kb
from states import PaymentFlow
from config import PAYMENT_CARD_NUMBER, PAYMENT_CARD_OWNER, ADMIN_GROUP_ID, BOOK_FILE_PATH

router = Router()


@router.callback_query(F.data == "pay_now")
async def cb_pay_now(callback: CallbackQuery, state: FSMContext):
    user = await db.get_user_by_tg_id(callback.from_user.id)
    if not user or user["is_blocked"]:
        await callback.answer("Amal bajarilmadi.", show_alert=True)
        return

    if await db.has_pending_or_approved_payment(user["id"]):
        await callback.answer("Sizning to'lovingiz allaqachon yuborilgan yoki tasdiqlangan.", show_alert=True)
        return

    await state.set_state(PaymentFlow.waiting_receipt)
    
    text = (
        "💳 <b>TO‘LOV MA’LUMOTLARI VA REKVIZITLAR</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Qabul qiluvchi karta:</b>\n"
        f"💳 <code>{PAYMENT_CARD_NUMBER}</code>\n"
        f"👤 <b>Karta egasi:</b> <b>{PAYMENT_CARD_OWNER}</b>\n\n"
        "<i>(Karta raqami ustiga bossangiz, avtomatik nusxalanadi)</i>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📥 <b>Keyingi qadam:</b>\n"
        "1. Yuqoridagi kartaga to‘lovni amalga oshiring.\n"
        "2. To‘lov chekini ushbu botga <b>rasm (JPG/PNG)</b> yoki <b>PDF hujjat</b> shaklida yuboring.\n"
        "2. To‘lov cheki tasdiqlangandan so'ng <b>elektron kitob</b> yuboriladi\n\n"
        "⚠️ <i>Chek aniq, summa va tranzaksiya vaqti ko‘ringan bo‘lishi shart.</i>\n\n"
        "🚫 Bekor qilish uchun: /cancel"
    )

    await callback.message.answer(text, parse_mode="HTML")


@router.message(PaymentFlow.waiting_receipt, F.photo | F.document)
async def process_receipt(message: Message, state: FSMContext, bot: Bot):
    user = await db.get_user_by_tg_id(message.from_user.id)
    if not user or user["is_blocked"]:
        return

    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    else:
        mime = (message.document.mime_type or "")
        if not (mime == "application/pdf" or mime.startswith("image/")):
            await message.answer("Faqat rasm yoki PDF formatidagi chek qabul qilinadi.")
            return
        file_id = message.document.file_id
        file_type = "document"

    payment_id = await db.create_payment(user["id"], file_id, file_type)
    await state.clear()

    caption = (
        "🧾 <b>Yangi to'lov cheki</b>\n\n"
        f"F.I.Sh: {user['fullname']}\n"
        f"Username: {'@' + user['username'] if user['username'] else '-'}\n"
        f"Telegram ID: <code>{user['telegram_id']}</code>\n"
        f"Telefon: {user['phone']}"
    )

    if file_type == "photo":
        sent = await bot.send_photo(
            ADMIN_GROUP_ID, file_id, caption=caption, parse_mode="HTML",
            reply_markup=kb.admin_review_kb(payment_id),
        )
    else:
        sent = await bot.send_document(
            ADMIN_GROUP_ID, file_id, caption=caption, parse_mode="HTML",
            reply_markup=kb.admin_review_kb(payment_id),
        )
    await db.set_payment_admin_message(payment_id, sent.message_id)

    await message.answer(
        "✅ Chekingiz qabul qilindi va tekshiruv uchun yuborildi.\n"
        "Adminlar tasdiqlagach sizga xabar beriladi. Iltimos kuting."
    )


@router.message(PaymentFlow.waiting_receipt)
async def process_receipt_invalid(message: Message):
    await message.answer("Iltimos, to'lov chekini rasm yoki PDF ko'rinishida yuboring. Bekor qilish uchun: /cancel")


@router.callback_query(F.data == "download_book")
async def cb_download_book(callback: CallbackQuery, bot: Bot):
    user = await db.get_user_by_tg_id(callback.from_user.id)
    if not user or not await db.is_participant(user["id"]):
        await callback.answer("Sizga hali ruxsat berilmagan.", show_alert=True)
        return

    cached_file_id = await db.get_setting("book_file_id")
    if cached_file_id:
        try:
            await bot.send_document(
                callback.from_user.id,
                cached_file_id,
                caption="📖 Kitobingiz tayyor! Uni tarqatish qat'iyan taqiqlanadi.",
                protect_content=True,
            )
            await db.mark_book_downloaded(user["id"])
            await callback.answer()
            return
        except Exception:
            pass

    if not os.path.exists(BOOK_FILE_PATH):
        await callback.answer("Kitob fayli topilmadi, admin bilan bog'laning.", show_alert=True)
        return

    sent_doc = await bot.send_document(
        callback.from_user.id,
        FSInputFile(BOOK_FILE_PATH),
        caption="📖 Kitobingiz tayyor! Uni tarqatish qat'iyan taqiqlanadi.",
        protect_content=True,
    )
    # File ID ni saqlab qo'yamiz
    await db.set_setting("book_file_id", sent_doc.document.file_id)
    await db.mark_book_downloaded(user["id"])
    await callback.answer()