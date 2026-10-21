"""
Ommaviy xabar yuborish (admin paneldan).

- Telegram limiti ~30 xabar/soniya: biz 25 tadan "paket" qilib, har paketni
  kamida 1 soniyada yuboramiz (flood control'dan oldini oladi).
- Flood control baribir chiqsa, safe_copy_message kutib qayta urinadi.
- Bloklagan foydalanuvchilar jim o'tkazib yuboriladi va hisobotda sanaladi.
- Bir vaqtda faqat BITTA ommaviy yuborish ishlaydi.
"""
import asyncio
import logging
import time

from aiogram import Bot

from utils.telegram_safe import safe_copy_message

logger = logging.getLogger(__name__)

BATCH_SIZE = 25
_lock = asyncio.Lock()
_tasks: set = set()


def is_running() -> bool:
    return _lock.locked()


async def run_broadcast(bot: Bot, admin_chat_id: int, from_chat_id: int, message_id: int,
                        recipients: list, title: str):
    async with _lock:
        total = len(recipients)
        ok = blocked = error = 0
        started = time.monotonic()
        progress_msg = await bot.send_message(admin_chat_id, f"📤 {title}: yuborish boshlandi (0/{total})...")

        for i in range(0, total, BATCH_SIZE):
            t0 = time.monotonic()
            batch = recipients[i:i + BATCH_SIZE]
            results = await asyncio.gather(
                *(safe_copy_message(bot, tg_id, from_chat_id, message_id) for tg_id in batch)
            )
            for r in results:
                if r == "ok":
                    ok += 1
                elif r == "blocked":
                    blocked += 1
                else:
                    error += 1

            done = i + len(batch)
            if (i // BATCH_SIZE) % 20 == 19 and done < total:
                try:
                    await progress_msg.edit_text(f"📤 {title}: {done}/{total} ...")
                except Exception:
                    pass

            elapsed = time.monotonic() - t0
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)

        secs = int(time.monotonic() - started)
        text = (
            f"✅ <b>{title} — yuborish yakunlandi</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 Jami: {total}\n"
            f"✅ Yetkazildi: {ok}\n"
            f"🚫 Yetkazilmadi (botni bloklagan/o'chirgan): {blocked}\n"
            f"⚠️ Xatolik: {error}\n"
            f"⏱ Vaqt: {secs // 60} daq {secs % 60} soniya"
        )
        try:
            await progress_msg.edit_text(text, parse_mode="HTML")
        except Exception:
            await bot.send_message(admin_chat_id, text, parse_mode="HTML")
        logger.info(f"[BROADCAST] {title}: jami={total} ok={ok} blocked={blocked} error={error}")


def start_background(coro):
    """Vazifani fonda ishga tushiradi va uni 'yig'ib yuborilishidan' saqlaydi."""
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task