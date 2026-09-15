"""Handlerlar orasida umumiy bo'lgan biznes-mantiq."""

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import Message

import storage as db
from utils import esc, pretty_date

log = logging.getLogger(__name__)


async def edit_safe(message: Message, text: str, **kwargs) -> None:
    """edit_text, lekin 'message is not modified' xatosini yutadi.

    Ro'yxat qayta chizilganda matn o'zgarmasligi mumkin — bu xato emas.
    """
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


async def send_safe(bot: Bot, chat_id: int, text: str, **kwargs) -> bool:
    """Xabar yuboradi va xatolikda botni yiqitmaydi.

    Bemor botni bloklagan bo'lsa yoki Telegram limitga urilsak — faqat log yoziladi.
    """
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except TelegramRetryAfter as e:
        log.warning("Telegram limiti: %s soniya kutilmoqda (chat_id=%s)", e.retry_after, chat_id)
        await asyncio.sleep(e.retry_after)
        try:
            await bot.send_message(chat_id, text, **kwargs)
            return True
        except Exception:
            log.exception("Qayta urinish ham muvaffaqiyatsiz (chat_id=%s)", chat_id)
            return False
    except TelegramForbiddenError:
        log.info("Foydalanuvchi botni bloklagan: chat_id=%s", chat_id)
        return False
    except Exception:
        log.exception("Xabar yuborilmadi: chat_id=%s", chat_id)
        return False


async def notify_admins(bot: Bot, text: str, exclude: int | None = None) -> None:
    """Barcha adminlarga xabar yuboradi (Telegram limitiga urilmaslik uchun oraliq bilan)."""
    for admin_id in await db.admin_ids():
        if admin_id == exclude:
            continue
        await send_safe(bot, admin_id, text)
        await asyncio.sleep(0.05)  # ~20 xabar/sekund


def booking_card(row, *, with_patient: bool = True) -> str:
    """Navbat haqidagi ma'lumotni HTML formatida chiroyli ko'rinishga keltiradi."""
    lines = [
        f"🏥 <b>Bo'lim:</b> {esc(row['service_name'])}",
        f"📅 <b>Kun:</b> {esc(pretty_date(row['booking_date']))}",
        f"⏰ <b>Soat:</b> {esc(row['booking_time'])}",
    ]
    if with_patient:
        lines.append(f"👤 <b>Bemor:</b> {esc(row['full_name'] or 'Ro‘yxatdan o‘tmagan')}")
        lines.append(f"📞 <b>Tel:</b> {esc(row['phone'] or '—')}")
    return "\n".join(lines)
