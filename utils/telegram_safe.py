"""
1000+ ishtirokchi bir vaqtda test boshlaganda, Telegram ba'zan
"Too Many Requests: retry after N" (juda tez-tez yuborilyapti) degan
vaqtinchalik cheklov qo'yishi mumkin. Agar bunga tayyor bo'lmasak,
o'sha foydalanuvchiga xabar UMUMAN YETIB BORMAY, "xatolik" deb
logga yozilib, o'tkazib yuborilardi — ya'ni ba'zi userlar testni
umuman boshlay olmasdan qolib ketishi mumkin edi.

Bu modul shu holatni avtomatik tuzatadi: agar Telegram "kuting" desa,
bot aynan shuncha vaqt kutib, so'ng AVTOMATIK qayta urinadi.
"""
import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramBadRequest

logger = logging.getLogger(__name__)

# Telegram bot uchun ~30 xabar/soniya chegarasini qo'yadi. Biz undan biroz pastroq
# (standart 25/s) tezlikda, NAVBAT bilan yuboramiz — shunda yuzlab foydalanuvchi
# bir vaqtda javob bersa ham flood control'ga tushmaymiz va hamma navbat bilan oladi.
# Kerak bo'lsa .env dagi TG_SEND_RATE orqali o'zgartiriladi.
import os as _os
import time as _time

SEND_RATE = float(_os.getenv("TG_SEND_RATE", "25"))


class _Pacer:
    """Barcha yuborishlar uchun yagona (global) tezlik cheklovchi."""

    def __init__(self, rate: float):
        self.interval = 1.0 / max(rate, 1.0)
        self._next = 0.0
        self._lock = None

    async def wait(self):
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            now = _time.monotonic()
            slot = max(now, self._next)
            self._next = slot + self.interval
        delay = slot - now
        if delay > 0:
            await asyncio.sleep(delay)

    def hold(self, seconds: float):
        """Telegram 'kuting' desa — BARCHA keyingi yuborishlar ham shuncha kutadi (to'dalanib qayta urinmaslik uchun)."""
        self._next = max(self._next, _time.monotonic() + seconds)


pacer = _Pacer(SEND_RATE)


async def safe_send_message(bot: Bot, chat_id: int, text: str, max_retries: int = 3, **kwargs):
    """
    bot.send_message ning "xavfsiz" varianti:
    - Telegram "juda tez yubordingiz, N soniyadan keyin urinib ko'ring" desa —
      aynan shuncha kutib, avtomatik qayta yuboradi (max_retries martagacha).
    - Foydalanuvchi botni bloklagan yoki chat topilmasa — bu KUTILGAN holat
      (ayb bizda emas), shunchaki jim o'tkazib yuboriladi, xato sifatida
      logga "qizil rangda" yozilmaydi.
    - Boshqa kutilmagan xato bo'lsa — logga yoziladi, lekin butun jarayon
      (boshqa userlarga yuborish) davom etaveradi.

    Muvaffaqiyatli bo'lsa yuborilgan xabar obyektini, aks holda None qaytaradi.
    """
    for attempt in range(max_retries + 1):
        try:
            await pacer.wait()
            return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
        except TelegramRetryAfter as e:
            pacer.hold(e.retry_after + 1)
            wait_time = e.retry_after + 1  # ehtiyot uchun +1 soniya
            logger.warning(
                f"[FLOOD CONTROL] chat={chat_id}: Telegram {e.retry_after}s kutishni so'radi "
                f"(urinish {attempt + 1}/{max_retries + 1}), kutib, qayta urinilmoqda..."
            )
            await asyncio.sleep(wait_time)
            # davom etadi -> keyingi urinish
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            # Foydalanuvchi botni bloklagan / o'chirgan / chat topilmadi -
            # bu bizning xatoligimiz emas, qayta urinishning ma'nosi yo'q.
            logger.info(f"[SKIP] chat={chat_id}: xabar yetkazib bo'lmadi ({e}), o'tkazib yuborildi.")
            return None
        except Exception as e:
            logger.error(f"[SEND ERROR] chat={chat_id}: kutilmagan xato: {e}")
            return None

    logger.error(f"[FLOOD CONTROL] chat={chat_id}: {max_retries} marta urinildi, baribir muvaffaqiyatsiz.")
    return None


async def safe_copy_message(bot: Bot, chat_id: int, from_chat_id: int, message_id: int, max_retries: int = 3):
    """
    Admin yuborgan xabarni (matn, rasm, video... — formati saqlangan holda)
    foydalanuvchiga NUSXALAB yuboradi. safe_send_message bilan bir xil mantiq:
    flood control bo'lsa kutib qayta urinadi, bloklagan foydalanuvchini jim o'tkazadi.

    Qaytaradi: "ok" | "blocked" (yetkazib bo'lmadi: bloklagan/chat yo'q) | "error"
    """
    for attempt in range(max_retries + 1):
        try:
            await pacer.wait()
            await bot.copy_message(chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id)
            return "ok"
        except TelegramRetryAfter as e:
            pacer.hold(e.retry_after + 1)
            logger.warning(f"[FLOOD CONTROL] copy chat={chat_id}: {e.retry_after}s kutilmoqda")
            await asyncio.sleep(e.retry_after + 1)
        except (TelegramForbiddenError, TelegramBadRequest):
            return "blocked"
        except Exception as e:
            logger.error(f"[COPY ERROR] chat={chat_id}: {e}")
            return "error"
    return "error"


async def safe_call(factory, max_retries: int = 3):
    """
    Istalgan Telegram chaqiruvini (callback.answer, edit_reply_markup, send_document...)
    flood-control'dan himoyalab bajaradi. `factory` — har urinishda yangi coroutine
    qaytaruvchi funksiya, masalan: safe_call(lambda: callback.answer("OK")).

    - "Too Many Requests: retry after N" bo'lsa, kutib qayta urinadi;
    - bloklagan/chat topilmadi/xabar o'zgarmagan kabi holatlarda jim None qaytaradi;
    - hech qachon exception ko'tarmaydi.
    """
    for attempt in range(max_retries + 1):
        try:
            return await factory()
        except TelegramRetryAfter as e:
            if attempt == max_retries:
                break
            await asyncio.sleep(e.retry_after + 1)
        except (TelegramForbiddenError, TelegramBadRequest):
            return None
        except Exception as e:
            logger.error(f"[SAFE CALL] kutilmagan xato: {e}")
            return None
    return None


async def safe_send_document(bot: Bot, chat_id: int, document, max_retries: int = 5, **kwargs):
    """send_document ning flood-control'dan himoyalangan varianti (natija PDF lari yo'qolmasligi uchun)."""
    async def _send():
        await pacer.wait()
        try:
            return await bot.send_document(chat_id, document, **kwargs)
        except TelegramRetryAfter as e:
            pacer.hold(e.retry_after + 1)
            raise

    return await safe_call(_send, max_retries=max_retries)