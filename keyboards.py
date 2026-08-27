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


def contest_intro_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🎯 Tanlovda ishtirok etish")]],
        resize_keyboard=True,
    )


def payment_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Keyingi bosqichga o'tish")]],
        resize_keyboard=True,
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


# Rad etish uchun tayyor sabablar: (kalit, tugma matni, foydalanuvchiga yuboriladigan to'liq matn)
# Admin bittasini tanlab bossa, shu matn foydalanuvchiga avtomatik yuboriladi —
# har safar qo'lda yozish shart emas.
REJECT_REASONS = [
    (
        "fake",
        "❌ Chek soxta (fake)",
        "Chek soxta (fake) — bunday to'lov tizimda ko'rinmadi. "
        "Iltimos, haqiqiy to'lov chekini qayta yuboring.",
    ),
    (
        "insufficient",
        "💰 Mablag' yetarli emas",
        "To'langan mablag' yetarli emas. Iltimos, belgilangan miqdorni to'liq "
        "to'lab, chekni qayta yuboring.",
    ),
    (
        "unclear",
        "📄 Chek noaniq/o'qilmaydi",
        "Chek tasviri noaniq, ma'lumotlarni o'qib bo'lmayapti. Iltimos, "
        "aniqroq va to'liq ko'rinadigan rasm bilan qayta yuboring.",
    ),
    (
        "wrong_card",
        "💳 Noto'g'ri kartaga to'langan",
        "To'lov noto'g'ri karta raqamiga yuborilgan. Iltimos, botda ko'rsatilgan "
        "to'g'ri karta raqamiga to'lov qilib, chekni qayta yuboring.",
    ),
    (
        "duplicate",
        "🔁 Bu chek allaqachon ishlatilgan",
        "Bu chek allaqachon boshqa ariza uchun ishlatilgan. Iltimos, o'zingiz "
        "amalga oshirgan haqiqiy to'lov chekini yuboring.",
    ),
]


def reject_reason_kb(payment_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"rejreason_{payment_id}_{key}")]
        for key, label, _ in REJECT_REASONS
    ]
    buttons.append(
        [InlineKeyboardButton(text="✏️ Boshqa sabab (o'zim yozaman)", callback_data=f"rejcustom_{payment_id}")]
    )
    buttons.append(
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data=f"rejback_{payment_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def post_approval_kb() -> ReplyKeyboardMarkup:
    """
    To'lov tasdiqlangandan keyingi doimiy pastki menyu.

    DIQQAT: ikkita alohida pastki menyuni ketma-ket yuborib bo'lmaydi —
    Telegram faqat ENG OXIRGI yuborilgan pastki menyuni ko'rsatadi, avvalgisi
    "yashiringan" bo'lib qoladi. Shu sababli "Kitobni yuklab olish" va
    "Testgacha vaqt" tugmalari BITTA menyuda, ikkita qatorda birlashtirildi.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📖 Kitobni yuklab olish")],
            [KeyboardButton(text="⏳ Testgacha qancha vaqt qoldi?")],
        ],
        resize_keyboard=True,
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