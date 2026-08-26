"""
PostgreSQL (asyncpg) bilan ishlash — YAGONA va TO'LIQ versiya.

MUHIM: bu fayl avvalgi database.py dagi bir necha marta qayta yozilgan
(bir xil nomli, bir-birini "bekor qilib" ketgan) funksiyalarni tozalab,
har bir handler (registration.py, contest.py, payment.py, admin.py,
test.py, leaderboard.py, scheduler.py) chaqirayotgan funksiya nomi va
argumentlar bilan ANIQ mos qilib qayta yozilgan.

Barcha user-qaytaruvchi funksiyalar oddiy dict qaytaradi (asyncpg.Record
emas), shunda .get() va boshqa dict metodlari ham xavfsiz ishlaydi.

Ustun nomi bazada `full_name`, lekin barcha handlerlar `user["fullname"]`
deb murojaat qiladi — shu sabab SELECT so'rovlarida doim
`full_name AS fullname` qilib olinadi.
"""
import time
import json
import logging
import asyncpg
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

logger = logging.getLogger(__name__)
pool: asyncpg.Pool = None


# ==================== JADVALLARNI YARATISH / MIGRATSIYA ====================

async def init_db():
    """
    PostgreSQL connection pool yaratish, jadvallarni ochish, va agar bazada
    eski (yetishmayotgan ustunli) jadvallar bo'lsa — ularni xavfsiz
    ravishda to'ldirish (ALTER TABLE ... ADD COLUMN IF NOT EXISTS).

    DIQQAT — MIGRATSIYA HAQIDA MUHIM ESLATMA:
    `results` jadvalidagi `started_at` / `finished_at` ustunlari avval TEXT
    turida edi (ISO matn), lekin test.py va pdf_generator.py bularni SON
    (epoch timestamp) sifatida ishlatadi — bu nomuvofiqlik hozirgi kunga
    qadar PDF yaratishda va vaqt hisoblashda xatoliklarga sabab bo'lgan.
    Shu sababli bu ikki ustun DOUBLE PRECISION turiga o'tkaziladi. Eski
    ustunlarda (agar bo'lsa) noto'g'ri/mos kelmaydigan matn qiymatlari
    bo'lgani uchun, ular xavfsiz tarzda o'chirilib qayta yaratiladi —
    bu FAQAT started_at/finished_at ustunlariga tegishli, boshqa hech
    qanday ma'lumot (userlar, to'lovlar, ishtirokchilar) o'chmaydi.
    Agar hozircha faol (in_progress) test topshirayotgan userlar bo'lsa,
    ularning testi qayta boshlanishi to'g'ri bo'ladi (bari bir avval bu
    ustunlar noto'g'ri ishlagani uchun ularning natijasi baribir noto'g'ri
    chiqqan bo'lardi).
    """
    global pool
    pool = await asyncpg.create_pool(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
        min_size=2, max_size=20,
    )

    async with pool.acquire() as conn:
        async with conn.transaction():
            # ---- Asosiy jadvallar (agar mavjud bo'lmasa yaratiladi) ----
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255),
                    full_name VARCHAR(255),
                    phone VARCHAR(50),
                    is_blocked BOOLEAN DEFAULT FALSE,
                    block_reason TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key VARCHAR(255) PRIMARY KEY,
                    value TEXT
                );

                CREATE TABLE IF NOT EXISTS payments (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    receipt_file_id TEXT,
                    file_type VARCHAR(20),
                    status VARCHAR(50) DEFAULT 'pending',
                    admin_id BIGINT,
                    admin_message_id BIGINT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS participants (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    status VARCHAR(50) DEFAULT 'approved',
                    book_downloaded BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS results (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    question_order TEXT,
                    answers_json TEXT DEFAULT '{}',
                    current_index INTEGER DEFAULT 0,
                    correct_count INTEGER DEFAULT 0,
                    wrong_count INTEGER DEFAULT 0,
                    unanswered_count INTEGER DEFAULT 0,
                    score DOUBLE PRECISION DEFAULT 0,
                    status VARCHAR(50) DEFAULT 'in_progress',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS user_answers (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    question_index INTEGER,
                    chosen_answer VARCHAR(10),
                    is_correct BOOLEAN,
                    answered_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            # ---- Eski bazalarda yetishmayotgan ustunlarni qo'shish ----
            await conn.execute("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(255);
                ALTER TABLE users ADD COLUMN IF NOT EXISTS block_reason TEXT;

                ALTER TABLE payments ADD COLUMN IF NOT EXISTS file_type VARCHAR(20);
                ALTER TABLE payments ADD COLUMN IF NOT EXISTS admin_message_id BIGINT;
                ALTER TABLE payments ADD COLUMN IF NOT EXISTS file_hash VARCHAR(64);

                ALTER TABLE participants ADD COLUMN IF NOT EXISTS book_downloaded BOOLEAN DEFAULT FALSE;

                ALTER TABLE results ADD COLUMN IF NOT EXISTS answers_json TEXT DEFAULT '{}';
                ALTER TABLE results ADD COLUMN IF NOT EXISTS correct_count INTEGER DEFAULT 0;
                ALTER TABLE results ADD COLUMN IF NOT EXISTS wrong_count INTEGER DEFAULT 0;
                ALTER TABLE results ADD COLUMN IF NOT EXISTS unanswered_count INTEGER DEFAULT 0;
            """)

            # ---- started_at / finished_at ni to'g'ri turga (SON) o'tkazish ----
            # Avval TEXT bo'lgan bo'lishi mumkin — mos kelmaydigan eski
            # qiymatlarni saqlashning ma'nosi yo'q (baribir noto'g'ri edi),
            # shuning uchun ustunni tur bilan birga qayta yaratamiz.
            col_type = await conn.fetchval("""
                SELECT data_type FROM information_schema.columns
                WHERE table_name='results' AND column_name='started_at'
            """)
            if col_type is not None and col_type != "double precision":
                logger.warning(
                    "MIGRATSIYA: results.started_at/finished_at eski turda "
                    f"({col_type}) topildi, DOUBLE PRECISION ga o'tkazilmoqda. "
                    "Bu ustunlardagi eski (noto'g'ri) qiymatlar tozalanadi."
                )
                await conn.execute("""
                    ALTER TABLE results DROP COLUMN IF EXISTS started_at;
                    ALTER TABLE results ADD COLUMN started_at DOUBLE PRECISION;
                    ALTER TABLE results DROP COLUMN IF EXISTS finished_at;
                    ALTER TABLE results ADD COLUMN finished_at DOUBLE PRECISION;
                """)
            else:
                await conn.execute("""
                    ALTER TABLE results ADD COLUMN IF NOT EXISTS started_at DOUBLE PRECISION;
                    ALTER TABLE results ADD COLUMN IF NOT EXISTS finished_at DOUBLE PRECISION;
                """)

            # score ustuni ham SON (float) bo'lishi kerak (NEGATIVE_MARK tufayli
            # kasr son bo'lishi mumkin) — agar INTEGER bo'lsa, DOUBLE ga o'tkazamiz
            score_type = await conn.fetchval("""
                SELECT data_type FROM information_schema.columns
                WHERE table_name='results' AND column_name='score'
            """)
            if score_type is not None and score_type not in ("double precision", "real"):
                await conn.execute(
                    "ALTER TABLE results ALTER COLUMN score TYPE DOUBLE PRECISION USING score::double precision;"
                )

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
                CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);
                CREATE INDEX IF NOT EXISTS idx_payments_hash ON payments(file_hash);
            """)

    logger.info("PostgreSQL: barcha jadvallar tayyor (yaratildi/tekshirildi).")


# ==================== FOYDALANUVCHILAR (USERS) ====================
# DIQQAT: handlerlar user["fullname"] va user["username"] deb murojaat
# qiladi, shuning uchun har doim shu nomlar bilan qaytariladi.

_USER_SELECT = """
    SELECT id, telegram_id, username, full_name AS fullname, phone,
           is_blocked, block_reason, created_at
    FROM users
"""


async def get_user_by_tg_id(telegram_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_USER_SELECT + " WHERE telegram_id = $1", telegram_id)
        return dict(row) if row else None


async def get_user_by_id(user_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_USER_SELECT + " WHERE id = $1", user_id)
        return dict(row) if row else None


async def create_user(telegram_id: int, username: str, fullname: str, phone: str):
    """
    registration.py aynan shu nomlar bilan (telegram_id, username, fullname,
    phone) chaqiradi — shuning uchun parametr nomlari ham shunga mos.
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (telegram_id, username, full_name, phone)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (telegram_id) DO UPDATE
            SET username = EXCLUDED.username,
                full_name = EXCLUDED.full_name,
                phone = EXCLUDED.phone
        """, telegram_id, username, fullname, phone)


async def set_user_blocked(user_id: int, is_blocked: bool, reason: str = None):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_blocked = $1, block_reason = $2 WHERE id = $3",
            is_blocked, reason, user_id,
        )


# ==================== TO'LOV VA CHEKLAR (PAYMENTS) ====================

async def has_pending_or_approved_payment(user_id: int) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM payments WHERE user_id=$1 AND status IN ('pending','approved') LIMIT 1",
            user_id,
        )
        return row is not None


async def create_payment(user_id: int, file_id: str, file_type: str, file_hash: str = None) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval("""
            INSERT INTO payments (user_id, receipt_file_id, file_type, file_hash, status)
            VALUES ($1, $2, $3, $4, 'pending')
            RETURNING id
        """, user_id, file_id, file_type, file_hash)


async def find_duplicate_receipts(file_hash: str, exclude_user_id: int):
    """
    Xuddi shu fayl (bir xil hash) BOSHQA foydalanuvchi(lar) tomonidan
    yuborilganmi tekshiradi — soxta/qayta ishlatilgan chek (masalan bitta
    skrinshotni ikki kishi yuborishi) ni aniqlash uchun.

    Faqat 'rejected' holatidagilar chetlab o'tiladi (chunki rad etilgan
    chek — allaqachon yaroqsiz deb topilgan, ogohlantirish keragi yo'q).
    Bir xil foydalanuvchining o'zi qayta yuborgan nusxalari
    (exclude_user_id) hisobga olinmaydi.
    """
    if not file_hash:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT p.id AS payment_id, p.status, p.user_id,
                   u.telegram_id, u.full_name AS fullname
            FROM payments p
            JOIN users u ON u.id = p.user_id
            WHERE p.file_hash = $1
              AND p.user_id != $2
              AND p.status != 'rejected'
            ORDER BY p.created_at ASC
        """, file_hash, exclude_user_id)
        return [dict(r) for r in rows]


async def set_payment_admin_message(payment_id: int, message_id: int):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE payments SET admin_message_id=$1 WHERE id=$2", message_id, payment_id
        )


async def get_payment(payment_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM payments WHERE id=$1", payment_id)
        return dict(row) if row else None


async def review_payment(payment_id: int, status: str, admin_id: int = None):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE payments SET status=$1, admin_id=$2, updated_at=NOW() WHERE id=$3
        """, status, admin_id, payment_id)


async def get_pending_payments():
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT p.*, u.full_name AS fullname, u.phone, u.telegram_id
            FROM payments p JOIN users u ON p.user_id = u.id
            WHERE p.status = 'pending' ORDER BY p.created_at ASC
        """)
        return [dict(r) for r in rows]


# ==================== ISHTIROKCHILAR (PARTICIPANTS) ====================

async def add_participant(user_id: int):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO participants (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING",
            user_id,
        )


async def get_all_participants():
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT p.user_id, u.telegram_id, u.full_name AS fullname, u.phone, u.is_blocked
            FROM participants p JOIN users u ON u.id = p.user_id
            WHERE u.is_blocked = FALSE
        """)
        return [dict(r) for r in rows]


async def is_participant(user_id: int) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM participants WHERE user_id=$1", user_id)
        return row is not None


async def mark_book_downloaded(user_id: int):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE participants SET book_downloaded=TRUE WHERE user_id=$1", user_id
        )


# ==================== TEST VA NATIJALAR (RESULTS) ====================

async def get_test_result(user_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM results WHERE user_id=$1", user_id)
        return dict(row) if row else None


async def start_test(user_id: int, order: list):
    """
    test.py: db.start_test(user_id, order) — order Python list.
    scheduler.py ham aynan shu funksiyani chaqiradi (create_or_reset_result
    o'rniga), shu bilan ikkala joy ham bir xil, to'g'ri ishlaydigan
    ma'lumot bilan test yozuvini yaratadi.
    """
    now = time.time()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO results
                (user_id, question_order, answers_json, current_index,
                 correct_count, wrong_count, unanswered_count, score,
                 status, started_at, finished_at)
            VALUES ($1, $2, '{}', 0, 0, 0, 0, 0, 'in_progress', $3, NULL)
            ON CONFLICT (user_id) DO UPDATE SET
                question_order = EXCLUDED.question_order,
                answers_json = '{}',
                current_index = 0,
                correct_count = 0,
                wrong_count = 0,
                unanswered_count = 0,
                score = 0,
                status = 'in_progress',
                started_at = EXCLUDED.started_at,
                finished_at = NULL
        """, user_id, json.dumps(order), now)


async def save_answer(user_id: int, q_index: int, answer: str, next_index: int, is_correct: bool):
    """
    test.py chaqiradi: db.save_answer(user_id, q_index, choice, step_index+1, is_correct)
    — argumentlar tartibi aynan shu: (user_id, q_index, answer, next_index, is_correct)
    """
    score_increment = 1 if is_correct else 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT answers_json FROM results WHERE user_id=$1 FOR UPDATE", user_id
            )
            answers = json.loads(row["answers_json"]) if row and row["answers_json"] else {}
            answers[str(q_index)] = answer

            await conn.execute("""
                UPDATE results
                SET current_index=$1,
                    correct_count = correct_count + $2,
                    answers_json=$3
                WHERE user_id=$4
            """, next_index, score_increment, json.dumps(answers), user_id)

            await conn.execute("""
                INSERT INTO user_answers (user_id, question_index, chosen_answer, is_correct)
                VALUES ($1, $2, $3, $4)
            """, user_id, q_index, answer, is_correct)


async def finish_test(user_id: int, correct: int, wrong: int, unanswered: int, score: float):
    """
    test.py chaqiradi: db.finish_test(user_id, correct, wrong, unanswered, score)
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE results
            SET status='finished', finished_at=$1,
                correct_count=$2, wrong_count=$3, unanswered_count=$4, score=$5
            WHERE user_id=$6
        """, time.time(), correct, wrong, unanswered, score, user_id)


async def get_all_in_progress_tests():
    """
    Vaqt tugaganda hali yakunlamagan ishtirokchilarni topish uchun
    (scheduler.py._end_test_for_all shu orqali ularga PDF/xabar yuboradi).
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT r.user_id, u.telegram_id
            FROM results r JOIN users u ON u.id = r.user_id
            WHERE r.status = 'in_progress' AND u.is_blocked = FALSE
        """)
        return [dict(r) for r in rows]


# ==================== REYTING VA STATISTIKA (LEADERBOARD) ====================

async def get_live_progress():
    """leaderboard.py — test davomida jonli holat."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT r.user_id, u.telegram_id, u.full_name AS fullname,
                   r.current_index, r.correct_count, r.status
            FROM results r JOIN users u ON u.id = r.user_id
            ORDER BY r.correct_count DESC, r.current_index DESC
        """)
        return [dict(r) for r in rows]


async def get_all_results_with_users():
    """admin.py — statistika va yakuniy PDF uchun to'liq ro'yxat."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT r.*, u.telegram_id, u.full_name AS fullname, u.username, u.phone
            FROM results r JOIN users u ON u.id = r.user_id
            ORDER BY r.score DESC, r.finished_at ASC NULLS LAST
        """)
        return [dict(r) for r in rows]


async def get_bot_stats():
    async with pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users;")
        total_participants = await conn.fetchval("SELECT COUNT(*) FROM participants;")
        finished_tests = await conn.fetchval("SELECT COUNT(*) FROM results WHERE status='finished';")
        return {
            "total_users": total_users or 0,
            "total_participants": total_participants or 0,
            "finished_tests": finished_tests or 0,
        }


# ==================== SOZLAMALAR (SETTINGS) ====================

async def get_setting(key: str, default: str = None):
    async with pool.acquire() as conn:
        val = await conn.fetchval("SELECT value FROM settings WHERE key=$1", key)
        return val if val is not None else default


async def set_setting(key: str, value: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO settings (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, key, str(value))