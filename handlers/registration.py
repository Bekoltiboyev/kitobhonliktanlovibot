from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

import database as db
import keyboards as kb
from states import Registration
from utils.subscription import is_user_subscribed
from config import PRIZE_TEXT

router = Router()


async def _show_registration_start(message: Message, state: FSMContext):
    await state.set_state(Registration.waiting_fullname)
    await message.answer(
        "Ro'yxatdan o'tish uchun to'liq ism-familiyangizni kiriting:\n"
        "(masalan: Aliyev Vali Aliyevich)"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    user = await db.get_user_by_tg_id(message.from_user.id)

    if user and user["is_blocked"]:
        await message.answer("⛔️ Siz botdan foydalanish huquqidan mahrum qilingansiz.")
        return

    if user:
        await message.answer(
            "Siz allaqachon ro'yxatdan o'tgansiz! 👇",
            reply_markup=kb.contest_intro_kb(),
        )
        return

    WELCOME_VIDEO_ID = "BAACAgQAAxkBAAIB..."  # O'zingizning haqiqiy file_id ingizni qo'ying
    try:
        await message.answer_video(
            video=WELCOME_VIDEO_ID,
            caption=(
                "🎉 <b>Tanlovimizga xush kelibsiz!</b>\n\n"
                "Videoni ko'rib chiqing va keyin ro'yxatdan o'tishni davom ettiring."
            ),
            parse_mode="HTML"
        )
    except Exception:
        # Video file_id xato bo'lsa bot to'xtab qolmaydi
        pass

    subscribed = await is_user_subscribed(bot, message.from_user.id)
    if not subscribed:
        await message.answer(
            "Botdan foydalanish uchun avval quyidagi kanalga obuna bo'ling, "
            "so'ng \"Tekshirish\" tugmasini bosing:",
            reply_markup=kb.channel_subscribe_kb(),
        )
        return

    await _show_registration_start(message, state)


@router.callback_query(F.data == "check_sub")
async def cb_check_sub(callback: CallbackQuery, state: FSMContext, bot: Bot):
    subscribed = await is_user_subscribed(bot, callback.from_user.id)
    if not subscribed:
        await callback.answer("Siz hali kanalga obuna bo'lmadingiz ❌", show_alert=True)
        return
    try:
        await callback.message.delete()
    except Exception:
        pass
    user = await db.get_user_by_tg_id(callback.from_user.id)
    if user:
        await callback.message.answer("Rahmat! Siz allaqachon ro'yxatdan o'tgansiz 👇",
                                       reply_markup=kb.contest_intro_kb())
        return
    await _show_registration_start(callback.message, state)


@router.message(Registration.waiting_fullname)
async def process_fullname(message: Message, state: FSMContext):
    fullname = message.text.strip() if message.text else ""
    if len(fullname.split()) < 2 or len(fullname) < 5:
        await message.answer("Iltimos to'liq ism-familiyangizni to'g'ri kiriting.")
        return
    await state.update_data(fullname=fullname)
    await state.set_state(Registration.waiting_phone)
    await message.answer(
        "Endi telefon raqamingizni yuboring (tugmani bosing):",
        reply_markup=kb.phone_request_kb(),
    )


@router.message(Registration.waiting_phone, F.contact)
async def process_phone(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    data = await state.get_data()
    fullname = data.get("fullname")

    await db.create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        fullname=fullname,
        phone=phone,
    )
    await state.clear()

    await message.answer("✅ Ro'yxatdan muvaffaqiyatli o'tdingiz!", reply_markup=ReplyKeyboardRemove())
    await message.answer(PRIZE_TEXT, parse_mode="HTML")
    await message.answer(
        "Tanlovda ishtirok etish uchun quyidagi tugmani bosing 👇",
        reply_markup=kb.contest_intro_kb(),
    )


@router.message(Registration.waiting_phone)
async def process_phone_invalid(message: Message):
    await message.answer("Iltimos, pastdagi \"📱 Raqamni yuborish\" tugmasi orqali yuboring.")


@router.message(F.video)
async def get_video_id(message: Message):
    await message.answer(
        f"🎥 Video file_id:\n\n<code>{message.video.file_id}</code>",
        parse_mode="HTML"
    )