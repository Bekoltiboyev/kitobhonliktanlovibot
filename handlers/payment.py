import os
import hashlib
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.fsm.context import FSMContext

import database as db
import keyboards as kb
from states import PaymentFlow
from config import PAYMENT_CARD_NUMBER, PAYMENT_CARD_OWNER, ADMIN_GROUP_ID, BOOK_FILE_PATH

logger = logging.getLogger(__name__)
router = Router()

MAX_RECEIPT_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


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
        "2. To‘lov chekini ushbu botga <b>rasm (JPG/PNG)</b> yoki <b>PDF hujjat</b> shaklida yuboring "
        "(fayl hajmi <b>5 MB</b> dan oshmasligi kerak).\n"
        "3. To‘lov cheki tasdiqlangandan so'ng <b>elektron kitob</b> yuboriladi\n\n"
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
        largest_photo = message.photo[-1]
        if largest_photo.file_size and largest_photo.file_size > MAX_RECEIPT_SIZE_BYTES:
            await message.answer(
                "⚠️ Rasm hajmi juda katta (5 MB dan oshmasligi kerak). "
                "Iltimos, hajmi kichikroq rasm yuboring yoki sifatini pasaytirib qayta yuboring."
            )
            return
        file_id = largest_photo.file_id
        file_type = "photo"
    else:
        mime = (message.document.mime_type or "")
        if not (mime == "application/pdf" or mime.startswith("image/")):
            await message.answer(
                "❌ Faqat rasm (JPG/PNG) yoki PDF formatidagi chek qabul qilinadi. "
                "Boshqa fayl turlari (video, arxiv, matn va h.k.) qabul qilinmaydi."
            )
            return
        if message.document.file_size and message.document.file_size > MAX_RECEIPT_SIZE_BYTES:
            await message.answer(
                "⚠️ Fayl hajmi juda katta (5 MB dan oshmasligi kerak). "
                "Iltimos, hajmi kichikroq fayl yuboring."
            )
            return
        file_id = message.document.file_id
        file_type = "document"

    # ---- Faylning "raqamli izi" (hash) ni hisoblaymiz — takroriy/soxta ----
    # chekni aniqlash uchun. Fayl mazmunining o'zi (piksellari) solishtiriladi,
    # Telegram file_id emas — chunki bitta faylni ikki marta yuborsangiz ham
    # file_id boshqacha bo'lishi mumkin, lekin mazmuni bir xil bo'lsa hash
    # ham bir xil chiqadi.
    file_hash = None
    try:
        file_bytes_io = await bot.download(file_id)
        file_hash = hashlib.sha256(file_bytes_io.read()).hexdigest()
    except Exception as e:
        logger.warning(f"[RECEIPT HASH] fayl yuklab olib hash hisoblashda xato: {e}")
        # Hash hisoblab bo'lmasa ham, chekning o'zini rad etmaymiz — faqat
        # takroriy tekshiruv shu chek uchun o'tkazib yuboriladi.

    payment_id = await db.create_payment(user["id"], file_id, file_type, file_hash)
    await state.clear()

    caption = (
        "🧾 <b>Yangi to'lov cheki</b>\n\n"
        f"F.I.Sh: {user['fullname']}\n"
        f"Username: {'@' + user['username'] if user['username'] else '-'}\n"
        f"Telegram ID: <code>{user['telegram_id']}</code>\n"
        f"Telefon: {user['phone']}"
    )

    # ---- Takroriy chek tekshiruvi ----
    if file_hash:
        duplicates = await db.find_duplicate_receipts(file_hash, exclude_user_id=user["id"])
        if duplicates:
            warn_lines = ["\n\n⚠️⚠️⚠️ <b>DIQQAT: XUDDI SHU CHEK BOSHQA FOYDALANUVCHI(LAR)DAN HAM KELGAN!</b>"]
            for d in duplicates:
                status_uz = {"pending": "kutilmoqda", "approved": "tasdiqlangan"}.get(d["status"], d["status"])
                warn_lines.append(
                    f"  • {d['fullname']} (ID: <code>{d['telegram_id']}</code>) — holati: {status_uz}"
                )
            warn_lines.append("\n👉 Ehtiyot bo'ling, bu soxta/qayta ishlatilgan chek bo'lishi mumkin!")
            caption += "\n".join(warn_lines)

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
    # Bu handler PaymentFlow.waiting_receipt holatida F.photo yoki F.document
    # bo'lmagan HAR QANDAY boshqa xabar turi uchun ishga tushadi — ya'ni matn,
    # video, ovozli xabar, sticker, joylashuv va hokazolar shu yerda "chek
    # sifatida qabul qilinmadi" deb rad etiladi.
    await message.answer(
        "❌ Faqat rasm yoki PDF formatidagi chek qabul qilinadi (hajmi 5 MB dan oshmasin). "
        "Boshqa hech qanday fayl turi qabul qilinmaydi.\n\n"
        "Bekor qilish uchun: /cancel"
    )


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