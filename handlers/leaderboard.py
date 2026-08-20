from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import database as db
from utils.questions import load_questions

router = Router()


@router.message(Command("leaderboard"))
async def cmd_leaderboard(message: Message):
    rows = await db.get_live_progress()
    if not rows:
        await message.answer("Hozircha test boshlanmagan yoki ishtirokchi yo'q.")
        return

    total_q = len(load_questions())
    lines = ["📊 <b>JONLI REYTING</b>\n"]
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for i, r in enumerate(rows, start=1):
        medal = medals.get(i, f"{i}.")
        progress = f"{r['current_index']}/{total_q}"
        status = "✅ tugatgan" if r["status"] == "finished" else f"⏳ {progress} savol"
        name = r["fullname"]
        lines.append(f"{medal} {name} — to'g'ri: {r['correct_count']} | {status}")

    finished_count = sum(1 for r in rows if r["status"] == "finished")
    lines.append(f"\n👥 Jami ishtirokchilar: {len(rows)} | Tugatganlar: {finished_count}")

    await message.answer("\n".join(lines), parse_mode="HTML")
