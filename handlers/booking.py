"""Navbat olish, ko'rish va bekor qilish."""

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import storage as db
import keyboards as kb
from callbacks import DateCB, DeptCB, SlotCB, UserBookingCB
from handlers.common import ask_phone
from services import booking_card, notify_admins
from utils import esc, is_slot_bookable, pretty_date

log = logging.getLogger(__name__)
router = Router(name="booking")


async def _require_registration(message: Message, state: FSMContext) -> bool:
    """Ro'yxatdan o'tmagan foydalanuvchini navbat olishga qo'ymaydi."""
    if await db.is_registered(message.from_user.id):
        return True
    await ask_phone(message, state)
    return False


@router.message(F.text == kb.BTN_BOOK)
async def start_booking(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not await _require_registration(message, state):
        return
    await message.answer("🏥 Qaysi bo'limga yozilmoqchisiz?", reply_markup=kb.departments())


@router.callback_query(DeptCB.filter())
async def choose_day(callback: CallbackQuery, callback_data: DeptCB) -> None:
    if db.department(callback_data.key) is None:
        await callback.answer("Bo'lim topilmadi.", show_alert=True)
        return

    await callback.message.edit_text(
        f"🏥 <b>Bo'lim:</b> {esc(db.dept_name(callback_data.key))}\n\n"
        f"Qaysi kunga navbat olmoqchisiz?",
        reply_markup=kb.days(callback_data.key),
    )
    await callback.answer()


@router.callback_query(DateCB.filter())
async def choose_slot(callback: CallbackQuery, callback_data: DateCB) -> None:
    booked = await db.booked_times(callback_data.key, callback_data.date)
    await callback.message.edit_text(
        f"🏥 <b>Bo'lim:</b> {esc(db.dept_name(callback_data.key))}\n"
        f"📅 <b>Kun:</b> {esc(pretty_date(callback_data.date))}\n\n"
        f"O'zingizga qulay soatni tanlang:\n"
        f"<i>🟢 bo'sh · ❌ band · ⌛ o'tib ketgan</i>",
        reply_markup=kb.slots(callback_data.key, callback_data.date, booked),
    )
    await callback.answer()


@router.callback_query(SlotCB.filter())
async def take_slot(callback: CallbackQuery, callback_data: SlotCB, bot: Bot) -> None:
    user_id = callback.from_user.id
    key, date_str, time_str = callback_data.key, callback_data.date, callback_data.time

    if not await db.is_registered(user_id):
        await callback.answer("Avval /start bosib telefon raqamingizni yuboring.", show_alert=True)
        return

    if not is_slot_bookable(date_str, time_str, db.rule("min_lead_minutes")):
        await callback.answer("Bu vaqt o'tib ketgan, boshqa soatni tanlang.", show_alert=True)
        await callback.message.edit_reply_markup(
            reply_markup=kb.slots(key, date_str, await db.booked_times(key, date_str))
        )
        return

    existing = await db.user_booking_on_date(user_id, date_str)
    if existing:
        await callback.answer(
            f"Siz bu kunga allaqachon soat {existing['booking_time']} ga yozilgansiz.", show_alert=True
        )
        return

    max_active = db.rule("max_active_bookings")
    if await db.count_active_bookings(user_id) >= max_active:
        await callback.answer(
            f"Sizda {max_active} ta faol navbat bor. Avval birini bekor qiling.", show_alert=True
        )
        return

    service_name = db.dept_name(key)
    app_id = await db.create_booking(user_id, key, service_name, date_str, time_str)

    # app_id is None -> shu soniyada boshqa bemor ulgurdi (atomar indeks ushladi)
    if app_id is None:
        await callback.answer("Afsuski, bu soat hozirgina band bo'ldi.", show_alert=True)
        await callback.message.edit_reply_markup(
            reply_markup=kb.slots(key, date_str, await db.booked_times(key, date_str))
        )
        return

    await callback.message.edit_text(
        f"🎉 <b>Navbat muvaffaqiyatli olindi!</b>\n\n"
        f"🏥 <b>Bo'lim:</b> {esc(service_name)}\n"
        f"📅 <b>Kun:</b> {esc(pretty_date(date_str))}\n"
        f"⏰ <b>Soat:</b> {esc(time_str)}\n"
        f"🔖 <b>Raqam:</b> #{app_id}\n\n"
        f"🔔 Navbatingiz kelganda shifokor shu bot orqali sizga xabar beradi.\n"
        f"Kelolmasangiz, «{kb.BTN_CANCEL}» tugmasi orqali bekor qiling."
    )
    await callback.answer("Navbat olindi ✅")

    booking = await db.get_booking(app_id)
    if booking:
        await notify_admins(bot, "🚨 <b>Yangi navbat!</b>\n\n" + booking_card(booking))


@router.message(F.text == kb.BTN_MY)
async def my_bookings(message: Message, state: FSMContext) -> None:
    await state.clear()
    rows = await db.active_bookings_of(message.from_user.id)
    if not rows:
        await message.answer("Sizda hozircha faol navbat yo'q.")
        return

    text = "📋 <b>Sizning faol navbatlaringiz:</b>\n\n"
    for row in rows:
        text += (
            f"🔖 #{row['id']} — {esc(row['service_name'])}\n"
            f"📅 {esc(pretty_date(row['booking_date']))}  ⏰ <b>{esc(row['booking_time'])}</b>\n\n"
        )
    await message.answer(text)


@router.message(F.text == kb.BTN_CANCEL)
async def cancel_prompt(message: Message, state: FSMContext) -> None:
    await state.clear()
    rows = await db.active_bookings_of(message.from_user.id)
    if not rows:
        await message.answer("Bekor qilish uchun faol navbatingiz yo'q.")
        return
    await message.answer("Qaysi navbatni bekor qilmoqchisiz?", reply_markup=kb.my_bookings_cancel(rows))


@router.callback_query(UserBookingCB.filter(F.action == "ask"))
async def cancel_confirm(callback: CallbackQuery, callback_data: UserBookingCB) -> None:
    booking = await db.get_booking(callback_data.id)

    # Egalik tekshiruvi: boshqa odamning navbati haqida ma'lumot ham bermaymiz
    if not booking or booking["user_id"] != callback.from_user.id or booking["status"] != "active":
        await callback.answer("Bu navbat topilmadi yoki sizga tegishli emas.", show_alert=True)
        return

    await callback.message.edit_text(
        "❓ <b>Rostdan bekor qilasizmi?</b>\n\n" + booking_card(booking, with_patient=False),
        reply_markup=kb.confirm_user_cancel(callback_data.id),
    )
    await callback.answer()


@router.callback_query(UserBookingCB.filter(F.action == "yes"))
async def cancel_apply(callback: CallbackQuery, callback_data: UserBookingCB, bot: Bot) -> None:
    booking = await db.get_booking(callback_data.id)

    # DIQQAT: user_id ham uzatiladi — shusiz istalgan odam boshqaning navbatini o'chira olardi
    if not await db.cancel_booking(callback_data.id, user_id=callback.from_user.id):
        await callback.answer("Bu navbat topilmadi yoki sizga tegishli emas.", show_alert=True)
        return

    await callback.message.edit_text("✅ Navbatingiz bekor qilindi. Soat boshqalar uchun bo'shatildi.")
    await callback.answer()

    if booking:
        await notify_admins(bot, "⚠️ <b>Navbat bekor qilindi</b>\n\n" + booking_card(booking))
