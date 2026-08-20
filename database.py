import asyncpg
import json
import logging
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

logger = logging.getLogger(__name__)
pool: asyncpg.Pool = None

async def init_db():
    """PostgreSQL connection pool yaratish va barcha asosiy jadvallarni ochish."""
    global pool
    pool = await asyncpg.create_pool(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        min_size=2,
        max_size=20
    )

    async with pool.acquire() as conn:
        # 1. Foydalanuvchilar jadvali
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                full_name VARCHAR(255),
                phone VARCHAR(50),
                is_blocked BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # 2. To'lovlar va cheklar jadvali
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                receipt_file_id TEXT,
                status VARCHAR(50) DEFAULT 'pending',
                admin_id BIGINT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # 3. Tasdiqlangan ishtirokchilar jadvali
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                id SERIAL PRIMARY KEY,
                user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                status VARCHAR(50) DEFAULT 'approved',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # 4. Test natijalari jadvali
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id SERIAL PRIMARY KEY,
                user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                question_order TEXT,
                current_index INTEGER DEFAULT 0,
                score INTEGER DEFAULT 0,
                status VARCHAR(50) DEFAULT 'in_progress',
                started_at TEXT,
                finished_at TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # 5. Har bir savolga berilgan batafsil javoblar jurnali
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_answers (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                question_index INTEGER,
                chosen_answer VARCHAR(10),
                is_correct BOOLEAN,
                answered_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

    logger.info("PostgreSQL: Barcha jadvallar muvaffaqiyatli ishga tushirildi.")


# ==================== FOYDALANUVCHILAR (USERS) ====================

async def get_user_by_telegram_id(telegram_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
        return dict(row) if row else None

async def get_user_by_id(user_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
        return dict(row) if row else None

async def add_or_update_user(telegram_id: int, full_name: str, phone: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO users (telegram_id, full_name, phone)
            VALUES ($1, $2, $3)
            ON CONFLICT (telegram_id) 
            DO UPDATE SET full_name = EXCLUDED.full_name, phone = EXCLUDED.phone
            RETURNING id;
        """, telegram_id, full_name, phone)
        return row["id"]

async def set_user_block_status(telegram_id: int, is_blocked: bool):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_blocked = $1 WHERE telegram_id = $2", is_blocked, telegram_id)


# ==================== TO'LOV VA CHEKLAR (PAYMENTS) ====================

async def add_payment(user_id: int, receipt_file_id: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO payments (user_id, receipt_file_id, status)
            VALUES ($1, $2, 'pending')
            RETURNING id;
        """, user_id, receipt_file_id)
        return row["id"]

async def update_payment_status(payment_id: int, status: str, admin_id: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE payments 
            SET status = $1, admin_id = $2, updated_at = NOW() 
            WHERE id = $3
        """, status, admin_id, payment_id)

async def get_pending_payments():
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT p.*, u.full_name, u.phone, u.telegram_id 
            FROM payments p
            JOIN users u ON p.user_id = u.id
            WHERE p.status = 'pending'
            ORDER BY p.created_at ASC
        """)
        return [dict(r) for r in rows]


# ==================== ISHTIROKCHILAR (PARTICIPANTS) ====================

async def add_participant(user_id: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO participants (user_id, status)
            VALUES ($1, 'approved')
            ON CONFLICT (user_id) DO NOTHING;
        """, user_id)

async def get_all_participants():
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT p.user_id, u.telegram_id, u.full_name, u.phone, u.is_blocked
            FROM participants p
            JOIN users u ON p.user_id = u.id
            WHERE u.is_blocked = FALSE
        """)
        return [dict(r) for r in rows]

async def is_participant(user_id: int) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM participants WHERE user_id = $1", user_id)
        return bool(row)


# ==================== TEST VA NATIJALAR (RESULTS) ====================

async def get_user_result(user_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM results WHERE user_id = $1", user_id)
        return dict(row) if row else None

async def create_or_reset_result(user_id: int, question_order: str, started_at: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO results (user_id, question_order, started_at, current_index, score, status)
            VALUES ($1, $2, $3, 0, 0, 'in_progress')
            ON CONFLICT (user_id) DO UPDATE SET
                question_order = EXCLUDED.question_order,
                started_at = EXCLUDED.started_at,
                current_index = 0,
                score = 0,
                status = 'in_progress',
                finished_at = NULL;
        """, user_id, question_order, started_at)

async def save_answer(user_id: int, q_index: int, answer: str, is_correct: bool, next_index: int):
    score_increment = 1 if is_correct else 0
    async with pool.acquire() as conn:
        # 1. Natijani yangilaymiz
        await conn.execute("""
            UPDATE results 
            SET current_index = $1,
                score = score + $2
            WHERE user_id = $3
        """, next_index, score_increment, user_id)

        # 2. Javoblar jurnaliga saqlaymiz
        await conn.execute("""
            INSERT INTO user_answers (user_id, question_index, chosen_answer, is_correct)
            VALUES ($1, $2, $3, $4)
        """, user_id, q_index, answer, is_correct)

async def finish_test(user_id: int, finished_at: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE results 
            SET status = 'finished', finished_at = $1 
            WHERE user_id = $2
        """, finished_at, user_id)


# ==================== REYTING VA STATISTIKA (LEADERBOARD) ====================

async def get_leaderboard_data():
    """PDF va umumiy reyting uchun saralangan ro'yxat."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT 
                u.full_name, 
                u.phone, 
                u.telegram_id, 
                r.score, 
                r.started_at, 
                r.finished_at,
                r.status
            FROM results r
            JOIN users u ON r.user_id = u.id
            ORDER BY r.score DESC, r.finished_at ASC
        """)
        return [dict(r) for r in rows]

async def get_bot_stats():
    """Admin panel uchun umumiy statistika."""
    async with pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users;")
        total_participants = await conn.fetchval("SELECT COUNT(*) FROM participants;")
        finished_tests = await conn.fetchval("SELECT COUNT(*) FROM results WHERE status = 'finished';")
        return {
            "total_users": total_users or 0,
            "total_participants": total_participants or 0,
            "finished_tests": finished_tests or 0
        }