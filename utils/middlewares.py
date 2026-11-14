"""
FullnameGuard — ismi (F.I.Sh) bazada bo'sh qolgan foydalanuvchilar uchun.

Ular botga istalgan xabar yoki tugma bilan murojaat qilsa, avval ism-familiyasini
so'raydi (telefon qayta so'ralmaydi). Ism kiritilgach, bot odatdagidek ishlaydi.
Adminlar va guruh/kanal xabarlari bu tekshiruvdan o'tkazib yuboriladi.
"""
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

import database as db
from config import ADMIN_IDS
from states import Registration


class FullnameGuard(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user_tg = getattr(event, "from_user", None)
        if user_tg is None or user_tg.id in ADMIN_IDS:
            return await handler(event, data)

        msg = event if isinstance(event, Message) else getattr(event, "message", None)
        if msg is None or msg.chat.type != "private":
            return await handler(event, data)

        user = await db.get_user_by_tg_id(user_tg.id)
        if not user or (user.get("fullname") or "").strip():
            return await handler(event, data)

        state = data.get("state")
        current = await state.get_state() if state else None
        if current and current.startswith("Registration:"):
            return await handler(event, data)

        if state:
            await state.clear()
            await state.set_state(Registration.waiting_fullname)
            await state.update_data(fix_name=True)
        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except Exception:
                pass
        await msg.answer(
            "❗️ Ism-familiyangiz tizimda saqlanmagan.\n\n"
            "Iltimos, to'liq ism-familiyangizni kiriting:\n"
            "(masalan: Aliyev Vali Aliyevich)"
        )
        return None


# ---------------------------------------------------------------------------
# SubscriptionGuard — kanalga obuna bo'lmaguncha bot hech narsaga javob bermaydi
# ---------------------------------------------------------------------------
import time
import logging
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from config import REQUIRED_CHANNEL
import keyboards as _kb

_sub_logger = logging.getLogger(__name__)

# Obuna bo'lgan foydalanuvchini shuncha soniya qayta tekshirmaymiz (Telegram'ga yuk tushmasligi uchun).
_SUB_CACHE_TTL = 120
_sub_cache: dict[int, float] = {}

_SUB_TEXT = (
    "📢 <b>Botdan foydalanish uchun avval kanalga obuna bo'ling.</b>\n\n"
    f"Kanal: {REQUIRED_CHANNEL}\n\n"
    "Obuna bo'lgach, \"✅ Tekshirish\" tugmasini bosing."
)


async def _is_member(bot, tg_id: int):
    """True/False — aniq javob. None — Telegram vaqtincha javob bermadi (tarmoq xatosi va h.k.)."""
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=tg_id)
        return member.status not in ("left", "kicked")
    except (TelegramBadRequest, TelegramForbiddenError):
        # Masalan: bot kanalda admin emas / kanal topilmadi — sozlash xatosi.
        _sub_logger.error("Obunani tekshirib bo'lmadi (bot kanalda admin emasmi?): %s", REQUIRED_CHANNEL)
        return False
    except Exception as e:
        _sub_logger.warning("Obuna tekshiruvi vaqtincha xato berdi (%s) — o'tkazib yuborildi", e)
        return None


class SubscriptionGuard(BaseMiddleware):
    """Kanalga obuna bo'lmagan foydalanuvchiga faqat 'obuna bo'ling' xabarini ko'rsatadi.

    O'tkazib yuboriladi: adminlar, guruh/kanal xabarlari, 'check_sub' tugmasi
    va test paytidagi javob tugmalari (ans_*) — 800 kishi har savolda Telegram'dan
    obuna so'rasa, test sekinlashib qolardi.
    """

    async def __call__(self, handler, event, data):
        user_tg = getattr(event, "from_user", None)
        if user_tg is None or user_tg.id in ADMIN_IDS:
            return await handler(event, data)

        msg = event if isinstance(event, Message) else getattr(event, "message", None)
        if msg is None or msg.chat.type != "private":
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            cb = event.data or ""
            if cb == "check_sub" or cb.startswith("ans_"):
                return await handler(event, data)

        now = time.monotonic()
        if _sub_cache.get(user_tg.id, 0) > now:
            return await handler(event, data)

        result = await _is_member(data["bot"], user_tg.id)
        if result is True or result is None:
            if result is True:
                _sub_cache[user_tg.id] = now + _SUB_CACHE_TTL
                if len(_sub_cache) > 50000:
                    _sub_cache.clear()
            return await handler(event, data)

        # Obuna emas — xabar ko'rsatamiz, handlerga o'tkazmaymiz.
        _sub_cache.pop(user_tg.id, None)
        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except Exception:
                pass
        try:
            await msg.answer(_SUB_TEXT, parse_mode="HTML", reply_markup=_kb.channel_subscribe_kb())
        except Exception:
            pass
        return None