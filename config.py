import os
from dotenv import load_dotenv
from zoneinfo import ZoneInfo


# .env faylni yuklash
load_dotenv()




DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "kitobxonlik_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

# Vaqt mintaqasi (O'zbekiston)
TZ_TASHKENT = ZoneInfo("Asia/Tashkent")


# ==== ASOSIY SOZLAMALAR ====
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN topilmadi! .env faylni tekshiring.")

# Admin/moderatorlarning telegram ID lari
ADMIN_IDS = [
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
]

# Adminlar to'lov cheklarini ko'radigan yopiq guruh ID si
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "0"))

# Majburiy obuna bo'lish kerak bo'lgan kanal
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@Bunyodkoravlod")


# To'lov kartasi ma'lumotlari
PAYMENT_CARD_NUMBER = os.getenv("PAYMENT_CARD_NUMBER", "")
PAYMENT_CARD_OWNER = os.getenv("PAYMENT_CARD_OWNER", "")

# Kitob va narxi
BOOK_NAME = os.getenv("BOOK_NAME", "Kitob nomi")
BOOK_PRICE = os.getenv("BOOK_PRICE", "0 so'm")

# Mukofotlar (e'lon matnida ishlatiladi)
PRIZE_TEXT = (
    "🎁 <b>TANLOVNING ASOSIY MUKOFOTLARI</b>\n\n"
    "\n"
    "  🥇 <b>1-o‘rin:</b> iPhone 17 Pro Max 📲\n"
    "  🥈 <b>2-o‘rin:</b> Gruziya / Batumiga yo‘llanma 🌴\n"
    "  🥉 <b>3-o‘rin:</b> HP Noutbuk 💻\n"
    "  🎖 <b>4-o‘rin:</b> Planshet 📲\n"
    "  🎖 <b>5-o‘rin:</b> Smart TV (43\") 📺\n"
    "\n\n"
    "📌 <i>G‘oliblar to‘plangan ballar va sarflangan eng kam vaqt bo‘yicha aniqlanadi.</i>"
)

# Test sozlamalari
TEST_DURATION_MINUTES = int(os.getenv("TEST_DURATION_MINUTES", "60"))
TOTAL_QUESTIONS = int(os.getenv("TOTAL_QUESTIONS", "60"))
NEGATIVE_MARK = float(os.getenv("NEGATIVE_MARK", "0"))

# Fayl va baza yo'llari
DB_PATH = os.getenv("DB_PATH", "bot_database.db")
QUESTIONS_FILE = os.getenv("QUESTIONS_FILE", "data/questions.json")
BOOK_FILE_PATH = os.getenv("BOOK_FILE_PATH", "data/book.pdf")
FONT_PATH_REGULAR = os.getenv("FONT_PATH_REGULAR", "data/fonts/DejaVuSans.ttf")
FONT_PATH_BOLD = os.getenv("FONT_PATH_BOLD", "data/fonts/DejaVuSans-Bold.ttf")