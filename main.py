import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv  # .env faylini o'qish uchun

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

# .env faylidagi o'zgaruvchilarni yuklash
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

MAP_LINK = "https://maps.app.goo.gl/Ay8YVsm44MMAWxst9?g_st=ac"
AVAILABLE_TIMES = ["09:00", "10:30", "12:00", "13:30", "15:00", "16:30", "18:00"]

bot = Bot(token=TOKEN)
dp = Dispatcher()


# --- DATABASE TIZIMI ---
def init_db():
    conn = sqlite3.connect("dental_bot.db")
    cursor = conn.cursor()

    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS users
                   (
                       user_id
                       INTEGER
                       PRIMARY
                       KEY,
                       full_name
                       TEXT,
                       phone
                       TEXT
                   )
                   """)

    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS queue_appointments
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       user_id
                       INTEGER,
                       booking_date
                       TEXT,
                       booking_time
                       TEXT,
                       status
                       TEXT
                       DEFAULT
                       'active',
                       UNIQUE
                   (
                       booking_date,
                       booking_time
                   )
                       )
                   """)
    conn.commit()
    conn.close()


# --- TUGMALAR ---
def get_main_menu(user_id):
    buttons = [
        [KeyboardButton(text="📅 Navbat olish")],
        [KeyboardButton(text="📋 Mening navbatim"), KeyboardButton(text="❌ Navbatni bekor qilish")],
        [KeyboardButton(text="📍 Manzil / Lokatsiya")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="👨‍⚕️ Admin Panel")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_phone_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def get_days_keyboard():
    keyboard = []
    today = datetime.now()

    # Keyingi 7 kun ichida Yakshanbadan tashqari kunlarni ko'rsatish
    for i in range(1, 8):
        day = today + timedelta(days=i)
        if day.weekday() != 6:  # 6 = Yakshanba (Dam olish kuni)
            day_str = day.strftime("%Y-%m-%d")
            weekdays_uz = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"]
            weekday_name = weekdays_uz[day.weekday()]

            button_text = f"📅 {weekday_name} ({day.strftime('%d.%m')})"
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"qdate_{day_str}")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_time_keyboard(selected_date):
    conn = sqlite3.connect("dental_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT booking_time FROM queue_appointments WHERE booking_date = ? AND status = 'active'",
                   (selected_date,))
    booked_times = [row[0] for row in cursor.fetchall()]
    conn.close()

    keyboard = []
    row = []
    for time_slot in AVAILABLE_TIMES:
        if time_slot in booked_times:
            row.append(InlineKeyboardButton(text=f"❌ {time_slot}", callback_data="booked_slot"))
        else:
            row.append(InlineKeyboardButton(text=f"🟢 {time_slot}", callback_data=f"take_{selected_date}_{time_slot}"))

        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- HANDLERLAR ---
@dp.message(CommandStart())
async def cmd_start(message: Message):
    conn = sqlite3.connect("dental_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT phone FROM users WHERE user_id = ?", (message.from_user.id,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        await message.answer(
            f"Assalomu alaykum, {message.from_user.first_name}!\n"
            "Stomatolog qabuliga yozilish uchun avval telefon raqamingizni yuboring:",
            reply_markup=get_phone_keyboard()
        )
    else:
        await message.answer(
            "Bosh menyu:",
            reply_markup=get_main_menu(message.from_user.id)
        )


@dp.message(F.contact)
async def process_contact(message: Message):
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    phone = message.contact.phone_number

    conn = sqlite3.connect("dental_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO users (user_id, full_name, phone) VALUES (?, ?, ?)",
        (user_id, full_name, phone)
    )
    conn.commit()
    conn.close()

    await message.answer(
        "Raqamingiz muvaffaqiyatli saqlandi!",
        reply_markup=get_main_menu(user_id)
    )


@dp.message(F.text == "📍 Manzil / Lokatsiya")
async def send_location(message: Message):
    await message.answer(
        f"📍 **Bizning manzilimiz:**\n\n"
        f"Klinikamiz joylashuvini Google Maps orqali ko'rish uchun quyidagi havolani bosing:\n\n"
        f"🔗 [Google Maps orqali ochish]({MAP_LINK})",
        parse_mode="Markdown",
        disable_web_page_preview=False
    )


@dp.message(F.text == "📅 Navbat olish")
async def start_queue(message: Message):
    await message.answer("Qaysi kunga navbat olmoqchisiz? Tanlang:", reply_markup=get_days_keyboard())


@dp.callback_query(F.data.startswith("qdate_"))
async def process_date(callback: CallbackQuery):
    selected_date = callback.data.split("qdate_")[1]

    await callback.message.edit_text(
        f"📅 **Tanlangan kun:** {selected_date}\n\n"
        f"Iltimos, o'zingizga qulay soatni tanlang:",
        parse_mode="Markdown",
        reply_markup=get_time_keyboard(selected_date)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("take_"))
async def take_queue(callback: CallbackQuery):
    _, selected_date, selected_time = callback.data.split("_")
    user_id = callback.from_user.id

    conn = sqlite3.connect("dental_bot.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT booking_time FROM queue_appointments WHERE user_id = ? AND booking_date = ? AND status = 'active'",
        (user_id, selected_date)
    )
    existing = cursor.fetchone()

    if existing:
        await callback.answer(f"Siz ushbu kunga allaqachon soat {existing[0]} ga navbat olgansiz!", show_alert=True)
        conn.close()
        return

    cursor.execute("SELECT full_name, phone FROM users WHERE user_id = ?", (user_id,))
    user_info = cursor.fetchone()

    try:
        cursor.execute(
            "INSERT INTO queue_appointments (user_id, booking_date, booking_time) VALUES (?, ?, ?)",
            (user_id, selected_date, selected_time)
        )
        conn.commit()

        await callback.message.edit_text(
            f"🎉 **Navbat muvaffaqiyatli olindi!**\n\n"
            f"📅 Kun: **{selected_date}**\n"
            f"⏰ Soat: **{selected_time}**\n\n"
            f"🔔 Qabul vaqtingiz kelganda shifokor bot orqali sizga ogohlantirish yuboradi!",
            parse_mode="Markdown"
        )

        if user_info and ADMIN_ID:
            name, phone = user_info
            admin_msg = (
                f"🚨 **Yangi navbat!**\n\n"
                f"👤 **Bemor:** {name}\n"
                f"📞 **Tel:** {phone}\n"
                f"📅 **Kun:** {selected_date}\n"
                f"⏰ **Soat:** {selected_time}"
            )
            await bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown")

    except sqlite3.IntegrityError:
        await callback.answer("Afsuski, bu soatdagi navbat band bo'lib qoldi!", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=get_time_keyboard(selected_date))
    finally:
        conn.close()


@dp.callback_query(F.data == "booked_slot")
async def booked_click(callback: CallbackQuery):
    await callback.answer("Bu vaqt band qilingan!", show_alert=True)


@dp.message(F.text == "📋 Mening navbatim")
async def show_my_queue(message: Message):
    user_id = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect("dental_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT booking_date, booking_time FROM queue_appointments WHERE user_id = ? AND status = 'active' AND booking_date >= ?",
        (user_id, today)
    )
    records = cursor.fetchall()
    conn.close()

    if not records:
        await message.answer("Sizda hozircha faol navbatlar yo'q.")
    else:
        text = "📋 **Sizning faol navbatlaringiz:**\n\n"
        for date, time_slot in records:
            text += f"📅 Kun: **{date}** | ⏰ Soat: **{time_slot}**\n"
        await message.answer(text, parse_mode="Markdown")


@dp.message(F.text == "❌ Navbatni bekor qilish")
async def cancel_queue_prompt(message: Message):
    user_id = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect("dental_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, booking_date, booking_time FROM queue_appointments WHERE user_id = ? AND status = 'active' AND booking_date >= ?",
        (user_id, today)
    )
    records = cursor.fetchall()
    conn.close()

    if not records:
        await message.answer("Bekor qilish uchun faol navbatingiz topilmadi.")
        return

    keyboard = []
    for app_id, date, time_slot in records:
        keyboard.append([InlineKeyboardButton(text=f"❌ {date} soat {time_slot} navbatini bekor qilish",
                                              callback_data=f"del_{app_id}")])

    await message.answer("Qaysi navbatni bekor qilmoqchisiz?",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


@dp.callback_query(F.data.startswith("del_"))
async def process_cancel(callback: CallbackQuery):
    app_id = int(callback.data.split("del_")[1])

    conn = sqlite3.connect("dental_bot.db")
    cursor = conn.cursor()

    cursor.execute(
        """SELECT qa.booking_date, qa.booking_time, u.full_name, u.phone, qa.user_id
           FROM queue_appointments qa
                    JOIN users u ON u.user_id = qa.user_id
           WHERE qa.id = ?""",
        (app_id,)
    )
    info = cursor.fetchone()

    cursor.execute("DELETE FROM queue_appointments WHERE id = ?", (app_id,))
    conn.commit()
    conn.close()

    await callback.message.edit_text("✅ Navbatingiz muvaffaqiyatli bekor qilindi.")

    if info:
        date, time_slot, name, phone, u_id = info

        if ADMIN_ID:
            admin_msg = (
                f"⚠️ **Navbat bekor qilindi!**\n\n"
                f"👤 **Bemor:** {name}\n"
                f"📞 **Tel:** {phone}\n"
                f"📅 **Kun:** {date}\n"
                f"⏰ **Soat:** {time_slot}"
            )
            await bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown")


# --- ADMIN PANEL ---
@dp.message(F.text == "👨‍⚕️ Admin Panel")
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    today = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect("dental_bot.db")
    cursor = conn.cursor()

    cursor.execute("""
                   SELECT qa.user_id, qa.booking_date, qa.booking_time, u.full_name, u.phone
                   FROM queue_appointments qa
                            JOIN users u ON u.user_id = qa.user_id
                   WHERE qa.booking_date >= ?
                     AND qa.status = 'active'
                   ORDER BY qa.booking_date ASC, qa.booking_time ASC
                   """, (today,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await message.answer("Hozircha olingan navbatlar yo'q.")
        return

    await message.answer("📋 **Olingan navbatlar ro'yxati (Chaqirish uchun tugmani bosing):**")

    for u_id, b_date, b_time, name, phone in rows:
        msg_text = (
            f"📅 **Kun:** {b_date}\n"
            f"⏰ **Soat:** {b_time}\n"
            f"👤 **Bemor:** {name}\n"
            f"📞 **Tel:** {phone}"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚨 Navbatingiz keldi (Chaqirish)", callback_data=f"notify_{u_id}_{b_time}")]
        ])
        await message.answer(msg_text, reply_markup=keyboard, parse_mode="Markdown")


# --- BEMORGA XABAR YUBORISH ---
@dp.callback_query(F.data.startswith("notify_"))
async def send_time_notification(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    _, target_user_id, time_slot = callback.data.split("_")
    target_user_id = int(target_user_id)

    try:
        user_msg = (
            "🚨 **SIZNING NAVBATINGIZ KELDI!**\n\n"
            "Shifokor sizni kutyapti, iltimos xonaga kiring."
        )

        await bot.send_message(chat_id=target_user_id, text=user_msg, parse_mode="Markdown")
        await callback.answer("Bemorga xabar yuborildi!", show_alert=True)
    except Exception as e:
        await callback.answer("Xabar yuborishda xatolik! Bemor botni bloklagan bo'lishi mumkin.", show_alert=True)


# --- ISHGA TUSHIRISH ---
async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
