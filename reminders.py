"""🔔 Avtomatik eslatmalar.

Bot bemorga navbat olayotganda «qabul vaqtingiz kelganda xabar beramiz» deb
va'da qiladi. Ilgari bu faqat admin tugmani qo'lda bosganda ishlardi —
endi bot o'zi eslatib turadi.

Ikki xil eslatma bor, ikkalasi ham panelda yoqib/o'chiriladi:
  * kun oldin — «ertaga navbatingiz bor»
  * soat oldin — «bir soatdan keyin qabul»

Har bir eslatma navbat yozuvida belgilanadi (`reminded`), shuning uchun
bot qayta ishga tushsa ham bir xil xabar ikki marta yuborilmaydi.
"""

import asyncio
import logging
from datetime import timedelta

from aiogram import Bot

import storage as db
from services import send_safe
from utils import esc, now, pretty_date, slot_datetime

log = logging.getLogger(__name__)

CHECK_INTERVAL = 60  # har daqiqada tekshiramiz — Telegram'ga yuk tushmaydi

# Kun oldingi eslatma qabuldan kamida shuncha vaqt oldin yuborilishi kerak.
# Busiz, bugunga yozilgan navbat uchun ham "ertaga navbatingiz bor" ketardi.
DAY_REMINDER_MIN_GAP = timedelta(hours=2)


def _day_text(booking: dict) -> str:
    return (
        "🔔 <b>Eslatma: ertaga qabulingiz bor</b>\n\n"
        f"🏥 {esc(booking['service_name'])}\n"
        f"📅 {esc(pretty_date(booking['booking_date']))}\n"
        f"⏰ <b>{esc(booking['booking_time'])}</b>\n\n"
        "Kelolmasangiz, iltimos «❌ Navbatni bekor qilish» orqali bekor qiling — "
        "o'rningiz boshqa bemorga bo'shaydi."
    )


def _hour_text(booking: dict, hours: int) -> str:
    when = "1 soatdan keyin" if hours == 1 else f"{hours} soatdan keyin"
    return (
        f"🔔 <b>Eslatma: {when} qabulingiz boshlanadi</b>\n\n"
        f"🏥 {esc(booking['service_name'])}\n"
        f"⏰ <b>{esc(booking['booking_time'])}</b>\n\n"
        "Iltimos, biroz oldinroq yetib keling."
    )


async def _send_due(bot: Bot) -> int:
    """Vaqti kelgan eslatmalarni yuboradi. Qaytaradi: yuborilganlar soni."""
    settings = db.reminders()
    day_on = bool(settings.get("day_before"))
    hours = int(settings.get("hours_before") or 0)

    if not day_on and hours <= 0:
        return 0

    moment = now()
    sent = 0

    for booking in db.active_future_bookings():
        try:
            slot = slot_datetime(booking["booking_date"], booking["booking_time"])
        except ValueError:
            continue

        if slot <= moment:
            continue  # o'tib ketgan

        reminded = booking.get("reminded") or {}
        left = slot - moment

        # --- Kun oldin ---
        if day_on and not reminded.get("day") and left <= timedelta(days=1):
            if left >= DAY_REMINDER_MIN_GAP:
                await db.mark_reminded(booking["id"], "day")
                if await send_safe(bot, booking["user_id"], _day_text(booking)):
                    sent += 1
                    log.info("Kunlik eslatma yuborildi: #%s", booking["id"])
            else:
                # Qabulga 2 soatdan kam qolgan — kunlik eslatma o'rinsiz,
                # uni yuborilgan deb belgilab qo'yamiz.
                await db.mark_reminded(booking["id"], "day")

        # --- Soat oldin ---
        if hours > 0 and not reminded.get("hour") and left <= timedelta(hours=hours):
            await db.mark_reminded(booking["id"], "hour")
            if await send_safe(bot, booking["user_id"], _hour_text(booking, hours)):
                sent += 1
                log.info("Soatlik eslatma yuborildi: #%s", booking["id"])

        await asyncio.sleep(0)  # event loop'ni bo'g'ib qo'ymaslik uchun

    return sent


class ReminderService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    async def _loop(self, bot: Bot) -> None:
        while True:
            try:
                await asyncio.sleep(CHECK_INTERVAL)
                sent = await _send_due(bot)
                if sent:
                    log.info("🔔 %d ta eslatma yuborildi", sent)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Eslatma siklida kutilmagan xato")

    def start(self, bot: Bot) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(bot), name="reminders")
            log.info("🔔 Eslatma xizmati ishga tushdi")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


reminders = ReminderService()
