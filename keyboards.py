from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from config import REQUIRED_CHANNEL


def channel_subscribe_kb() -> InlineKeyboardMarkup:
    channel_username = REQUIRED_CHANNEL.lstrip("@")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Tanlov xaqida yangiliklarni bilish uchun kanalga obuna bo'ling ",
                                   url=f"https://t.me/{channel_username}")],
            [InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")],
        ]
    )


def phone_request_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def contest_intro_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Tanlovda ishtirok etish", callback_data="join_contest")]
        ]
    )


def payment_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Keyingi bosqichga o'tish", callback_data="pay_now")]
        ]
    )


def admin_review_kb(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_{payment_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_{payment_id}"),
            ],
            [InlineKeyboardButton(text="🚫 Foydalanuvchini bloklash", callback_data=f"block_{payment_id}")],
        ]
    )


def download_book_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📖 Kitobni yuklab olish", callback_data="download_book")],
        ]
    )


def start_test_info_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏳ Testgacha qancha vaqt qoldi?", callback_data="time_left")]
        ]
    )


def question_kb(q_index: int, options: dict) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"{k}) {v}", callback_data=f"ans_{q_index}_{k}")]
        for k, v in options.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)



from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⏳ Test vaqtini belgilash", callback_data="admin_set_time"),
                InlineKeyboardButton(text="📥 Excel savollar yuklash", callback_data="admin_upload_excel"),
            ],
            [
                InlineKeyboardButton(text="📊 Yakuniy natijalar (PDF)", callback_data="admin_final_pdf"),
                InlineKeyboardButton(text="📈 Jonli statistika", callback_data="admin_stats"),
            ],
            [
                InlineKeyboardButton(text="🚫 Foydalanuvchini bloklash", callback_data="admin_block_user"),
                InlineKeyboardButton(text="✅ Blokdan chiqarish", callback_data="admin_unblock_user"),
            ]
        ]
    )

def admin_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_cancel")]
        ]
    )