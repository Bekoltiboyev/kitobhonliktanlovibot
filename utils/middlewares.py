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