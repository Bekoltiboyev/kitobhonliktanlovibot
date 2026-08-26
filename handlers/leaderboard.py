import datetime as dt

import database as db
from utils.questions import load_questions
from config import TOTAL_QUESTIONS

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


async def get_leaderboard_data(limit: int = None):
    """
    Jonli reyting uchun tayyor ma'lumot ro'yxatini qaytaradi.
    Har bir element: {place, fullname, correct, current_index, total, status}

    DIQQAT: "total" (savollar soni) TOTAL_QUESTIONS (config.py) va savollar
    hovuzi hajmidan kichigi olinadi — chunki test.py/scheduler.py har bir
    foydalanuvchiga BUTUN hovuzdan emas, faqat TOTAL_QUESTIONS tasini
    tasodifiy tanlab beradi (masalan hovuzda 300 ta savol bo'lsa ham, har
    bir user faqat 60 tasini oladi). Agar bu yerda hovuz hajmining o'zi
    ishlatilsa (masalan 300), jonli reyting "current_index/300" deb noto'g'ri
    ko'rsatgan bo'lardi, holbuki foydalanuvchiga atigi 60 ta savol berilgan.
    """
    rows = await db.get_live_progress()
    total_q = min(TOTAL_QUESTIONS, len(load_questions()))
    data = []
    for i, r in enumerate(rows, start=1):
        if limit and i > limit:
            break
        data.append({
            "place": i,
            "fullname": r["fullname"],
            "telegram_id": r["telegram_id"],
            "correct": r["correct_count"],
            "current_index": r["current_index"],
            "total": total_q,
            "status": r["status"],
        })
    return {
        "participants": data,
        "total_participants": len(rows),
        "finished_count": sum(1 for r in rows if r["status"] == "finished"),
        "updated_at": dt.datetime.now().strftime("%H:%M:%S"),
    }


def format_leaderboard_text(data: dict, limit: int = 20) -> str:
    """Telegram xabari uchun matn shaklida formatlash."""
    participants = data["participants"]
    if not participants:
        return "📊 <b>JONLI REYTING</b>\n\nHozircha test boshlanmagan yoki ishtirokchi yo'q."

    lines = ["📊 <b>JONLI REYTING</b>", ""]
    for p in participants[:limit]:
        medal = MEDALS.get(p["place"], f"{p['place']}.")
        status = "✅ tugatgan" if p["status"] == "finished" else f"⏳ {p['current_index']}/{p['total']} savol"
        lines.append(f"{medal} {p['fullname']} — to'g'ri: {p['correct']} | {status}")

    remaining = data["total_participants"] - min(limit, len(participants))
    if remaining > 0:
        lines.append(f"\n... va yana {remaining} ishtirokchi")

    lines.append(
        f"\n👥 Jami: {data['total_participants']} | Tugatgan: {data['finished_count']} "
        f"| 🕐 {data['updated_at']}"
    )
    return "\n".join(lines)