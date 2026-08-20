from aiogram import Bot
from config import REQUIRED_CHANNEL


async def is_user_subscribed(bot: Bot, telegram_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=telegram_id)
        return member.status not in ("left", "kicked")
    except Exception:
        # Bot kanalda admin bo'lmasa yoki xatolik yuz bersa, xavfsiz tomonga o'tamiz:
        # obuna emas deb hisoblab, foydalanuvchidan qayta urinishni so'raymiz.
        return False
