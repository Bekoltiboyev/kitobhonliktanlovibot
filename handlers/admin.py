import html
import inspect
import os
import asyncio
import datetime as dt
import tempfile

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.fsm.context import FSMContext

import database as db
import keyboards as kb
from states import AdminFlow
from config import ADMIN_IDS, ADMIN_GROUP_ID, TZ_TASHKENT
from utils.questions import parse_excel_questions
from utils import broadcast as bc

router = Router()


def admin_only(func):
    sig = inspect.signature(func)
    accepted_params = set(sig.parameters.keys())
    accepts_var_kwargs = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )

    async def wrapper(event, **kwargs):
        user_id = event.from_user.id
        if user_id not in ADMIN_IDS:
            if isinstance(event, CallbackQuery):
                await event.answer("Sizga ruxsat yo'q.", show_alert=True)
            return
        filtered = kwargs if accepts_var_kwargs else {k: v for k, v in kwargs.items() if k in accepted_params}
        return await func(event, **filtered)
    return wrapper


# ---------- ASOSIY ADMIN PANEL ----------

async def _panel_text_and_kb():
    """Admin panel matni va tugmalari (ro'yxatdan o'tish holati bilan)."""
    saved_time = await db.get_setting("test_start_time", "Belgilanmagan")
    reg_open = await db.is_registration_open()
    reg_status = "✅ Ochiq" if reg_open else "🔒 Yopiq"
    pay_open = await db.is_payment_open()
    pay_status = "✅ Ochiq" if pay_open else "🔒 Yopiq"
    text = (
        "🛠 <b>BOT BOSHQARUV PANELI (ADMIN)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ <b>Test boshlanish vaqti:</b> <code>{saved_time}</code>\n"
        f"📝 <b>Ro'yxatdan o'tish:</b> {reg_status}\n"
        f"💳 <b>To'lov qabuli:</b> {pay_status}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Kerakli bo'limni tanlang 👇"
    )
    return text, kb.admin_panel_kb(registration_open=reg_open, payment_open=pay_open)


@router.message(Command("admin"))
async def cmd_admin_panel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    text, markup = await _panel_text_and_kb()
    await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data == "admin_toggle_reg")
@admin_only
async def cb_toggle_registration(callback: CallbackQuery):
    """Ro'yxatdan o'tishni ochish/yopish. Allaqachon ro'yxatdan o'tganlarga ta'sir qilmaydi."""
    new_state = not await db.is_registration_open()
    await db.set_registration_open(new_state)
    text, markup = await _panel_text_and_kb()
    try:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer(
        "✅ Ro'yxatdan o'tish OCHILDI" if new_state else "🔒 Ro'yxatdan o'tish YOPILDI",
        show_alert=True,
    )


@router.callback_query(F.data == "admin_toggle_pay")
@admin_only
async def cb_toggle_payment(callback: CallbackQuery):
    """To'lov qabulini ochish/yopish. Allaqachon yuborilgan cheklarni ko'rib chiqish davom etadi."""
    new_state = not await db.is_payment_open()
    await db.set_payment_open(new_state)
    text, markup = await _panel_text_and_kb()
    try:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer(
        "✅ To'lov qabuli OCHILDI" if new_state else "🔒 To'lov qabuli YOPILDI",
        show_alert=True,
    )


@router.callback_query(F.data == "admin_cancel")
@admin_only
async def cb_admin_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Amal bekor qilindi.")
    await callback.answer()


# ---------- STATISTIKA ----------

@router.callback_query(F.data == "admin_stats")
@admin_only
async def cb_admin_stats(callback: CallbackQuery):
    stats = await db.get_bot_stats()
    participants = await db.get_all_participants()
    results = await db.get_all_results_with_users()
    finished = [r for r in results if r["status"] == "finished"]
    in_progress = [r for r in results if r["status"] == "in_progress"]

    text = (
        "📈 <b>BOTNING JORIY STATISTIKASI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆕 <b>Ro'yxatdan o'tganlar:</b> {stats['total_users']} nafar\n"
        f"💰 <b>To'lov qilib tasdiqlanganlar:</b> {len(participants)} nafar\n"
        f"📝 <b>Test topshirayotganlar:</b> {len(in_progress)} nafar\n"
        f"🏁 <b>Testni yakunlaganlar:</b> {len(finished)} nafar\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_paid_pdf")
@admin_only
async def cb_paid_pdf(callback: CallbackQuery):
    """To'lov qilib, tasdiqlangan barcha foydalanuvchilar ro'yxatini PDF holida beradi."""
    participants = await db.get_all_participants_full()
    if not participants:
        await callback.message.answer("Hozircha to'lov qilib tasdiqlangan foydalanuvchi yo'q.")
        await callback.answer()
        return

    await callback.message.answer("⏳ Hisobot tayyorlanmoqda, biroz kuting...")
    await callback.answer()

    from utils.pdf_generator import generate_participants_pdf
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "tolov_qilganlar.pdf")
        # DIQQAT: generate_participants_pdf ni ODDIY (to'g'ridan-to'g'ri)
        # chaqirish YUZLAB-MINGLAB qatorli hisobotda BUTUN BOTNI bir necha
        # soniyaga "muzlatib" qo'yardi — bu vaqtda hech qanday boshqa
        # foydalanuvchiga (ro'yxatdan o'tish, to'lov, test) javob berilmasdi,
        # chunki bot bitta oqimda (event loop) ishlaydi. asyncio.to_thread
        # orqali PDF generatsiya ALOHIDA oqimda ishlaydi, bot esa shu vaqtda
        # boshqa hamma bilan bemalol ishlashda davom etadi.
        await asyncio.to_thread(generate_participants_pdf, path, participants)
        await callback.message.answer_document(
            FSInputFile(path),
            caption=f"💰 To'lov qilganlar hisoboti — jami {len(participants)} nafar",
        )



# ---------- OMMAVIY XABAR YUBORISH ----------

_BC_TITLES = {"all": "Hammaga xabar", "paid": "To'lov qilganlarga xabar"}


async def _bc_start(callback: CallbackQuery, state: FSMContext, target: str):
    if bc.is_running():
        await callback.answer("Hozir boshqa ommaviy yuborish davom etmoqda. Tugashini kuting.", show_alert=True)
        return
    recipients = await db.get_broadcast_recipients(only_paid=(target == "paid"))
    await state.clear()
    await state.update_data(bc_target=target)
    await state.set_state(AdminFlow.waiting_broadcast_message)
    who = "to'lov qilgan ishtirokchilarga" if target == "paid" else "ro'yxatdan o'tgan barcha foydalanuvchilarga"
    await callback.message.answer(
        f"📢 <b>{_BC_TITLES[target]}</b>\n"
        f"Qabul qiluvchilar: <b>{len(recipients)}</b> nafar ({who})\n\n"
        "Yuboriladigan xabarni yuboring (matn, rasm yoki video — izoh bilan). "
        "Avval sizga ko'rib chiqish uchun ko'rsatiladi.",
        reply_markup=kb.admin_cancel_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_bc_all")
@admin_only
async def cb_bc_all(callback: CallbackQuery, state: FSMContext):
    await _bc_start(callback, state, "all")


@router.callback_query(F.data == "admin_bc_paid")
@admin_only
async def cb_bc_paid(callback: CallbackQuery, state: FSMContext):
    await _bc_start(callback, state, "paid")


@router.message(AdminFlow.waiting_broadcast_message)
@admin_only
async def process_bc_message(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target = data.get("bc_target", "all")
    recipients = await db.get_broadcast_recipients(only_paid=(target == "paid"))
    await state.update_data(bc_msg_id=message.message_id, bc_chat_id=message.chat.id)
    await state.set_state(AdminFlow.confirm_broadcast)

    await message.answer("👁 <b>Ko'rib chiqish</b> — foydalanuvchilarga aynan shunday ko'rinadi:", parse_mode="HTML")
    try:
        await bot.copy_message(message.chat.id, message.chat.id, message.message_id)
    except Exception as e:
        await state.clear()
        await message.answer(f"❌ Bu turdagi xabarni yuborib bo'lmaydi: {e}")
        return
    await message.answer(
        f"Yuborilsinmi? <b>{_BC_TITLES[target]}</b> — <b>{len(recipients)}</b> nafar qabul qiluvchi.\n"
        f"Taxminiy vaqt: ~{max(1, len(recipients) // 25)} soniya.",
        reply_markup=kb.broadcast_confirm_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_bc_confirm")
@admin_only
async def cb_bc_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    msg_id = data.get("bc_msg_id")
    chat_id = data.get("bc_chat_id")
    target = data.get("bc_target", "all")
    if not msg_id:
        await callback.answer("Sessiya tugagan, qaytadan boshlang.", show_alert=True)
        await state.clear()
        return
    if bc.is_running():
        await callback.answer("Boshqa ommaviy yuborish davom etmoqda.", show_alert=True)
        return

    recipients = await db.get_broadcast_recipients(only_paid=(target == "paid"))
    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer("Yuborish boshlandi 🚀")
    bc.start_background(
        bc.run_broadcast(bot, callback.message.chat.id, chat_id, msg_id, recipients, _BC_TITLES[target])
    )


# ---------- TEST VAQTINI O'RNATISH ----------

@router.callback_query(F.data == "admin_set_time")
@admin_only
async def cb_set_time_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFlow.waiting_test_time)
    await callback.message.answer(
        "⏳ Yangi test boshlanish vaqtini quyidagi formatda yuboring:\n\n"
        "<code>YYYY-MM-DD HH:MM</code>\n"
        "Masalan: <code>2026-08-25 20:00</code>",
        reply_markup=kb.admin_cancel_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminFlow.waiting_test_time)
@admin_only
async def process_new_test_time(message: Message, state: FSMContext, bot: Bot, scheduler=None):
    text = message.text.strip()
    try:
        naive_time = dt.datetime.strptime(text, "%Y-%m-%d %H:%M")
        test_time = naive_time.replace(tzinfo=TZ_TASHKENT)
    except ValueError:
        await message.answer("❌ Format xato! Qaytadan kiriting (Masalan: <code>2026-08-25 20:00</code>):", parse_mode="HTML")
        return

    await db.set_setting("test_start_time", test_time.isoformat())

    if scheduler is not None:
        from utils.scheduler import reschedule_test_jobs
        await reschedule_test_jobs(scheduler, bot, test_time)

    await state.clear()
    await message.answer(f"✅ <b>Test vaqti muvaffaqiyatli saqlandi:</b>\n{test_time.strftime('%Y-%m-%d %H:%M')} (Toshkent vaqti)", parse_mode="HTML")


# ---------- EXCEL FAYL YUKLASH ----------

@router.callback_query(F.data == "admin_upload_excel")
@admin_only
async def cb_upload_excel_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFlow.waiting_excel_file)
    await callback.message.answer(
        "📥 60 ta savol joylashtirilgan <b>.xlsx</b> Excel faylni yuboring:",
        reply_markup=kb.admin_cancel_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminFlow.waiting_excel_file, F.document)
@admin_only
async def process_excel_upload(message: Message, state: FSMContext, bot: Bot):
    doc = message.document
    safe_name = os.path.basename(doc.file_name or "")
    if not (safe_name.endswith(".xlsx") or safe_name.endswith(".xls")):
        await message.answer("Iltimos, faqat <b>.xlsx</b> formatdagi fayl yuboring.", parse_mode="HTML")
        return

    msg = await message.answer("⏳ Fayl tekshirilmoqda...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        file_path = os.path.join(tmp_dir, safe_name)
        await bot.download(doc, destination=file_path)
        success, info_text, count = parse_excel_questions(file_path)

        if success:
            await msg.edit_text(
                f"✅ <b>Savollar bazaga yuklandi!</b>\n\n"
                f"📊 Savollar soni: <b>{count} ta</b>\n"
                f"📁 Fayl: <code>{doc.file_name}</code>",
                parse_mode="HTML"
            )
            await state.clear()
        else:
            await msg.edit_text(f"❌ <b>Xatolik yuz berdi:</b>\n{info_text}", parse_mode="HTML")


# ---------- YAKUNIY PDF HISOBOT ----------

@router.callback_query(F.data == "admin_final_pdf")
@admin_only
async def cb_final_pdf(callback: CallbackQuery):
    results = await db.get_all_results_with_users()
    finished = [dict(r) for r in results if r["status"] == "finished"]
    if not finished:
        await callback.answer("Hali yakunlangan natijalar mavjud emas.", show_alert=True)
        return

    msg = await callback.message.answer("⏳ PDF hisobot tayyorlanmoqda...")
    from utils.pdf_generator import generate_admin_results_pdf
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "yakuniy_natijalar.pdf")
        await asyncio.to_thread(generate_admin_results_pdf, path, finished)
        await callback.message.answer_document(FSInputFile(path), caption="📊 <b>Tanlovning yakuniy natijalari</b>", parse_mode="HTML")
        await msg.delete()
    await callback.answer()


# ---------- BLOKLASH VA BLOKDAN CHIQARISH ----------

@router.callback_query(F.data == "admin_block_user")
@admin_only
async def cb_block_user_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFlow.waiting_manual_block)
    await callback.message.answer(
        "🚫 Bloklamoqchi bo'lgan foydalanuvchining <b>Telegram ID</b> raqamini va sababini yuboring:\n\n"
        "Format: <code>ID Sabab</code>\n"
        "Masalan: <code>123456789 Soxta chek yuborgan</code>",
        reply_markup=kb.admin_cancel_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminFlow.waiting_manual_block)
@admin_only
async def process_manual_block(message: Message, state: FSMContext):
    parts = message.text.split(maxsplit=1)
    try:
        tg_id = int(parts[0])
    except ValueError:
        await message.answer("❌ ID raqam bo'lishi kerak. Qaytadan kiriting:")
        return

    reason = parts[1] if len(parts) > 1 else "Qoidabuzarlik"
    user = await db.get_user_by_tg_id(tg_id)
    if not user:
        await message.answer("❌ Bunday foydalanuvchi topilmadi.")
        return

    await db.set_user_blocked(user["id"], True, reason)
    await state.clear()
    await message.answer(f"🚫 <b>{user['fullname']}</b> foydalanuvchisi bloklandi.", parse_mode="HTML")


@router.callback_query(F.data == "admin_unblock_user")
@admin_only
async def cb_unblock_user_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFlow.waiting_manual_unblock)
    await callback.message.answer(
        "✅ Blokdan chiqarmoqchi bo'lgan foydalanuvchining <b>Telegram ID</b> raqamini yuboring:",
        reply_markup=kb.admin_cancel_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminFlow.waiting_manual_unblock)
@admin_only
async def process_manual_unblock(message: Message, state: FSMContext):
    try:
        tg_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ ID faqat raqamlardan iborat bo'lishi kerak.")
        return

    user = await db.get_user_by_tg_id(tg_id)
    if not user:
        await message.answer("❌ Foydalanuvchi topilmadi.")
        return

    await db.set_user_blocked(user["id"], False, None)
    await state.clear()
    await message.answer(f"✅ <b>{user['fullname']}</b> blokdan chiqarildi.", parse_mode="HTML")


# ---------- TO'LOV CHEKLARINI TEKSHIRISH (GURUHDAGI TUGMALAR) ----------

@router.callback_query(F.data.startswith("approve_"))
@admin_only
async def cb_approve(callback: CallbackQuery, bot: Bot):
    payment_id = int(callback.data.split("_")[1])
    payment = await db.get_payment(payment_id)
    if not payment or payment["status"] != "pending":
        await callback.answer("Bu chek allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    if not await db.review_payment(payment_id, "approved", callback.from_user.id):
        await callback.answer("Bu chek allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    await db.add_participant(payment["user_id"])

    user = await db.get_user_by_id(payment["user_id"])
    try:
        await callback.message.edit_caption(
            caption=(callback.message.caption or "")
            + f"\n\n✅ <b>TASDIQLANDI</b> (Admin: {html.escape(callback.from_user.full_name or '', quote=False)})",
            reply_markup=None,
            parse_mode="HTML",
        )
    except Exception:
        pass
    try:
        await bot.send_message(
            user["telegram_id"],
            "✅ To'lovingiz tasdiqlandi! Endi kitobingizni yuklab olishingiz "
            "yoki testgacha qancha vaqt qolganini bilish uchun pastdagi tugmalardan foydalaning 👇",
            reply_markup=kb.post_approval_kb(),
        )
    except Exception:
        pass
    await callback.answer("Tasdiqlandi ✅")


async def _reject_payment(bot: Bot, payment_id: int, admin_id: int, reason_text: str):
    """
    Rad etishning umumiy mantig'i — bazani yangilash va foydalanuvchiga
    xabar yuborish. Ham tayyor sabab tugmasi, ham qo'lda yozilgan matn
    shu bitta funksiya orqali ishlaydi — ikkalasida ham bir xil natija
    kafolatlanadi.
    """
    payment = await db.get_payment(payment_id)
    if not payment:
        return False
    if not await db.review_payment(payment_id, "rejected", admin_id):
        return False  # allaqachon tasdiqlangan/rad etilgan — qayta o'zgartirilmaydi
    user = await db.get_user_by_id(payment["user_id"])
    try:
        await bot.send_message(
            user["telegram_id"],
            f"❌ To'lov chekingiz rad etildi.\nSabab: {html.escape(reason_text or '', quote=False)}\n\n"
            "Iltimos, to'lovni qayta tekshirib, to'g'ri chekni qayta yuboring.",
            reply_markup=kb.payment_kb(),
        )
    except Exception:
        pass
    return True


@router.callback_query(F.data.startswith("reject_"))
@admin_only
async def cb_reject_start(callback: CallbackQuery):
    """
    'Rad etish' bosilganda endi to'g'ridan-to'g'ri matn so'ralmaydi —
    avval tayyor sabablar menyusi ko'rsatiladi, shunda admin tezroq va
    bir xil, tushunarli matnlar bilan javob bera oladi.
    """
    payment_id = int(callback.data.split("_")[1])
    payment = await db.get_payment(payment_id)
    if not payment or payment["status"] != "pending":
        await callback.answer("Bu chek allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    await callback.message.edit_reply_markup(reply_markup=kb.reject_reason_kb(payment_id))
    await callback.answer()


@router.callback_query(F.data.startswith("rejback_"))
@admin_only
async def cb_reject_back(callback: CallbackQuery):
    """Sabablar menyusidan asosiy (Tasdiqlash/Rad etish/Bloklash) menyuga qaytish."""
    payment_id = int(callback.data.split("_")[1])
    await callback.message.edit_reply_markup(reply_markup=kb.admin_review_kb(payment_id))
    await callback.answer()


@router.callback_query(F.data.startswith("rejreason_"))
@admin_only
async def cb_reject_reason_selected(callback: CallbackQuery, bot: Bot):
    """Admin tayyor sabablardan birini tanlab bosdi."""
    _, payment_id_str, key = callback.data.split("_", 2)
    payment_id = int(payment_id_str)

    payment = await db.get_payment(payment_id)
    if not payment or payment["status"] != "pending":
        await callback.answer("Bu chek allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    reason_map = {k: text for k, _, text in kb.REJECT_REASONS}
    reason_text = reason_map.get(key)
    if not reason_text:
        await callback.answer("Noma'lum sabab.", show_alert=True)
        return

    await _reject_payment(bot, payment_id, callback.from_user.id, reason_text)
    try:
        await callback.message.edit_caption(
            caption=(callback.message.caption or "") + f"\n\n❌ <b>RAD ETILDI</b>\nSabab: {html.escape(reason_text, quote=False)}",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer("Rad etildi, foydalanuvchiga xabar yuborildi ❌")


@router.callback_query(F.data.startswith("rejcustom_"))
@admin_only
async def cb_reject_custom(callback: CallbackQuery, state: FSMContext):
    """Admin 'Boshqa sabab (o'zim yozaman)' tugmasini bosdi — eski, qo'lda yozish oqimi."""
    payment_id = int(callback.data.split("_")[1])
    payment = await db.get_payment(payment_id)
    if not payment or payment["status"] != "pending":
        await callback.answer("Bu chek allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    await state.update_data(reject_payment_id=payment_id)
    await state.set_state(AdminFlow.waiting_reject_reason)
    await callback.message.reply("Rad etish sababini yozing (foydalanuvchiga yuboriladi):")
    await callback.answer()


@router.message(AdminFlow.waiting_reject_reason)
@admin_only
async def process_reject_reason(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    payment_id = data.get("reject_payment_id")

    ok = await _reject_payment(bot, payment_id, message.from_user.id, message.text)
    if not ok:
        await state.clear()
        await message.reply("Bu chek allaqachon ko'rib chiqilgan (yoki topilmadi) — o'zgartirilmadi.")
        return

    await message.reply("Foydalanuvchiga xabar yuborildi ❌")
    await state.clear()


@router.callback_query(F.data.startswith("block_"))
@admin_only
async def cb_block_start(callback: CallbackQuery, state: FSMContext):
    payment_id = int(callback.data.split("_")[1])
    payment = await db.get_payment(payment_id)
    if not payment:
        await callback.answer()
        return
    await state.update_data(block_user_id=payment["user_id"])
    await state.set_state(AdminFlow.waiting_block_reason)
    await callback.message.reply("Bloklash sababini yozing (masalan: yolg'on chek):")
    await callback.answer()


@router.message(AdminFlow.waiting_block_reason)
@admin_only
async def process_block_reason(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user_id = data.get("block_user_id")
    user = await db.get_user_by_id(user_id)
    if not user:
        await state.clear()
        return

    await db.set_user_blocked(user_id, True, message.text)
    try:
        await bot.send_message(
            user["telegram_id"],
            f"⛔️ Siz botdan foydalanish huquqidan mahrum qilindingiz.\nSabab: {html.escape(message.text or '', quote=False)}",
        )
    except Exception:
        pass
    await message.reply(f"Foydalanuvchi {user['fullname']} bloklandi 🚫")
    await state.clear()


# import json
# import datetime as dt
# from aiogram import types, F
# from aiogram.filters import Command
# import aiosqlite

# import database as db
# import config  # config ni to'g'ridan-to'g'ri import qilamiz
# from utils.questions import load_questions


# @router.message(Command("make_winner"))
# async def cmd_make_winner(message: types.Message):
#     admin_list = getattr(config, "ADMINS", []) or getattr(config, "ADMIN_IDS", [])
#     single_admin = getattr(config, "ADMIN_ID", None)

#     is_admin = (message.from_user.id in admin_list) or (message.from_user.id == single_admin)
#     if not is_admin:
#         return

#     args = message.text.strip().split()
#     if len(args) < 2:
#         await message.answer("Format: <code>/make_winner TELEGRAM_ID</code>", parse_mode="HTML")
#         return

#     try:
#         target_tg_id = int(args[1])
#     except ValueError:
#         await message.answer("❌ ID faqat raqam bo'lishi kerak.")
#         return

#     # 1. Foydalanuvchini bazadan tekshirish
#     user = await db.get_user_by_telegram_id(target_tg_id)
#     if not user:
#         await message.answer(f"❌ <code>{target_tg_id}</code> bazada topilmadi. U avval botga /start bosishi kerak.")
#         return

#     u_data = dict(user)
#     user_id = u_data.get("id", user[0])
    
#     full_name = (
#         u_data.get("full_name") 
#         or u_data.get("name") 
#         or u_data.get("fio") 
#         or u_data.get("username") 
#         or f"User_{target_tg_id}"
#     )

#     # 2. Savollar sonini olish
#     questions = load_questions()
#     total_q = len(questions) if questions else 30
#     order = list(range(total_q))
    
#     tz = getattr(config, "TZ_TASHKENT", dt.timezone(dt.timedelta(hours=5)))
#     now_iso = dt.datetime.now(tz).isoformat()

#     # 3. Faqat results jadvaliga 100% natija yozish
#     db_name = getattr(db, "DB_NAME", "database.db")
#     async with aiosqlite.connect(db_name) as conn:
#         await conn.execute("DELETE FROM results WHERE user_id = ?", (user_id,))
#         await conn.execute("""
#             INSERT INTO results (user_id, question_order, current_index, score, status, started_at, finished_at)
#             VALUES (?, ?, ?, ?, 'finished', ?, ?)
#         """, (user_id, json.dumps(order), total_q, total_q, now_iso, now_iso))
#         await conn.commit()

#     await message.answer(
#         f"🏆 <b>G'olib muvaffaqiyatli belgilandi!</b>\n\n"
#         f"👤 <b>Ism:</b> {full_name}\n"
#         f"🆔 <b>ID:</b> <code>{target_tg_id}</code>\n"
#         f"📊 <b>Ball:</b> {total_q}/{total_q} (100%)\n"
#         f"📌 <b>Holat:</b> finished (Yakunlangan)",
#         parse_mode="HTML"
#     )


# ---------- HALI TASDIQLANMAGAN CHEKLARNI QAYTA CHIQARISH ----------
#
# MUAMMO: agar adminlar guruhida kimdir ko'plab xabarni birdan tanlab
# o'chirsa (masalan Telegram'ning "bir nechtasini tanlash" funksiyasi
# orqali), hali "kutilmoqda" (pending) holatidagi cheklar ham
# ko'rinishdan yo'qolib qolishi mumkin. Chekning o'zi (fayl, foydalanuvchi
# ma'lumoti, holati) BAZADA saqlanib qoladi — faqat Telegramdagi xabar
# yo'qoladi. /pending buyrug'i shu "yo'qolgan" cheklarni bazadan qidirib,
# ularni QAYTA, xuddi yangi kelgandek, tugmalari bilan birga chiqarib
# beradi — hech qanday ma'lumot yo'qolmaydi.


@router.message(Command("pending"))
async def cmd_pending(message: Message, bot: Bot):
    if message.from_user.id not in ADMIN_IDS:
        return

    pending = await db.get_pending_payments()
    if not pending:
        await message.answer("✅ Hozircha kutilayotgan (tasdiqlanmagan) chek yo'q.")
        return

    await message.answer(
        f"🔁 {len(pending)} ta kutilayotgan chek topildi, qaytadan chiqarilmoqda..."
    )

    for p in pending:
        phone_raw = str(p.get("phone") or "").strip()
        phone_display = phone_raw if phone_raw.startswith("+") else f"+{phone_raw}"
        caption = (
            "🧾 <b>To'lov cheki (qayta chiqarildi)</b>\n\n"
            f"F.I.Sh: {p['fullname']}\n"
            f"Username: {'@' + p['username'] if p.get('username') else '-'}\n"
            f"Telegram ID: <code>{p['telegram_id']}</code>\n"
            f"Telefon: {phone_display}"
        )
        try:
            if p["file_type"] == "photo":
                sent = await bot.send_photo(
                    ADMIN_GROUP_ID, p["receipt_file_id"], caption=caption, parse_mode="HTML",
                    reply_markup=kb.admin_review_kb(p["id"]),
                )
            else:
                sent = await bot.send_document(
                    ADMIN_GROUP_ID, p["receipt_file_id"], caption=caption, parse_mode="HTML",
                    reply_markup=kb.admin_review_kb(p["id"]),
                )
            await db.set_payment_admin_message(p["id"], sent.message_id)
        except Exception as e:
            await message.answer(
                f"⚠️ {p['fullname']} (ID: {p['telegram_id']}) ning chekini qayta chiqarishda "
                f"xatolik: {e}"
            )

    await message.answer("✅ Barcha kutilayotgan cheklar qayta chiqarildi.")