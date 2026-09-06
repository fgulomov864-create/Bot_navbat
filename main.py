import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
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

TOKEN = "8927832190:AAHlgvae0QQ44apPhzk7H5tfH09TTJ7XveM"
ADMIN_ID = 7437501484 # Akangizning Telegram ID'si

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
                       queue_number
                       INTEGER,
                       status
                       TEXT
                       DEFAULT
                       'active',
                       UNIQUE
                   (
                       booking_date,
                       queue_number
                   )
                       )
                   """)
    conn.commit()
    conn.close()


# --- TUGMALAR ---
def get_main_menu(user_id):
    buttons = [
        [KeyboardButton(text="📅 Navbat olish")],
        [KeyboardButton(text="📋 Mening navbatim"), KeyboardButton(text="❌ Navbatni bekor qilish")]
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
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    keyboard = [
        [InlineKeyboardButton(text="📅 Ertaga", callback_data=f"qdate_{tomorrow}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_queue_keyboard(selected_date):
    conn = sqlite3.connect("dental_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT queue_number FROM queue_appointments WHERE booking_date = ? AND status = 'active'",
                   (selected_date,))
    booked_numbers = [row[0] for row in cursor.fetchall()]
    conn.close()

    keyboard = []
    row = []
    for num in range(1, 21):
        if num in booked_numbers:
            row.append(InlineKeyboardButton(text=f"❌ {num}", callback_data="booked_num"))
        else:
            row.append(InlineKeyboardButton(text=f"🟢 {num}", callback_data=f"take_{selected_date}_{num}"))

        if len(row) == 4:
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
        "Raqamingiz saqlandi!",
        reply_markup=get_main_menu(user_id)
    )


@dp.message(F.text == "📅 Navbat olish")


async def start_queue(message: Message):
    await message.answer("Navbat olish uchun tugmani bosing:", reply_markup=get_days_keyboard())


@dp.callback_query(F.data.startswith("qdate_"))
async def process_date(callback: CallbackQuery):
    selected_date = callback.data.split("qdate_")[1]

    await callback.message.edit_text(
        f"📅 Tanlangan kun: Ertaga\nBo'sh navbat raqamini tanlang (1-20):",
        parse_mode="Markdown",
        reply_markup=get_queue_keyboard(selected_date)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("take_"))
async def take_queue(callback: CallbackQuery):
    _, selected_date, num = callback.data.split("_")
    num = int(num)
    user_id = callback.from_user.id

    conn = sqlite3.connect("dental_bot.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT queue_number FROM queue_appointments WHERE user_id = ? AND booking_date = ? AND status = 'active'",
        (user_id, selected_date)
    )
    existing = cursor.fetchone()

    if existing:
        await callback.answer(f"Siz ertangi kunga allaqachon {existing[0]}-sonli navbatni olgansiz!", show_alert=True)
        conn.close()
        return

    cursor.execute("SELECT full_name, phone FROM users WHERE user_id = ?", (user_id,))
    user_info = cursor.fetchone()

    try:
        cursor.execute(
            "INSERT INTO queue_appointments (user_id, booking_date, queue_number) VALUES (?, ?, ?)",
            (user_id, selected_date, num)
        )
        conn.commit()

        await callback.message.edit_text(
            f"🎉 Navbat muvaffaqiyatli olindi!\n\n"
            f"📅 Kun: Ertaga\n"
            f"🔢 Navbat raqamingiz: {num}-navbat\n\n"
            f"🔔 Qabul vaqtingiz yaqinlashganda doktor bot orqali sizga xabar yuboradi!",
            parse_mode="Markdown"
        )

        if user_info and ADMIN_ID:
            name, phone = user_info
            admin_msg = (
                f"🚨 Yangi navbat!\n\n"
                f"👤 Bemor: {name}\n"
                f"📞 Tel: {phone}\n"
                f"📅 Kun: Ertaga ({selected_date})\n"
                f"🔢 Navbat raqami: {num}"
            )
            await bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown")

    except sqlite3.IntegrityError:
        await callback.answer("Afsuski, bu navbat raqami band bo'lib qoldi!", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=get_queue_keyboard(selected_date))
    finally:
        conn.close()


@dp.callback_query(F.data == "booked_num")
async def booked_click(callback: CallbackQuery):
    await callback.answer("Bu navbat raqami band!", show_alert=True)


@dp.message(F.text == "📋 Mening navbatim")
async def show_my_queue(message: Message):
    user_id = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect("dental_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT booking_date, queue_number FROM queue_appointments WHERE user_id = ? AND status = 'active' AND booking_date >= ?",
        (user_id, today)
    )
    records = cursor.fetchall()
    conn.close()

    if not records:
        await message.answer("Sizda hozircha faol navbatlar yo'q.")
    else:
        text = "📋 Sizning faol navbatlaringiz:\n\n"
        for date, num in records:
            text += f"📅 Kun: Ertaga | 🔢 Navbat: {num}-sonli\n"
        await message.answer(text, parse_mode="Markdown")


@dp.message(F.text == "❌ Navbatni bekor qilish")
async def cancel_queue_prompt(message: Message):
    user_id = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect("dental_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, booking_date, queue_number FROM queue_appointments WHERE user_id = ? AND status = 'active' AND booking_date >= ?",
        (user_id, today)
    )
    records = cursor.fetchall()
    conn.close()

    if not records:
        await message.answer("Bekor qilish uchun faol navbatingiz topilmadi.")
        return

    keyboard = []
    for app_id, date, num in records:
        keyboard.append([InlineKeyboardButton(text=f"❌ Ertangi kungi {num}-navbatni bekor qilish", callback_data=f"del_{app_id}")])

    await message.answer("Qaysi navbatni bekor qilmoqchisiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@dp.callback_query(F.data.startswith("del_"))
async def process_cancel(callback: CallbackQuery):
    app_id = int(callback.data.split("del_")[1])

    conn = sqlite3.connect("dental_bot.db")
    cursor = conn.cursor()

    cursor.execute(
        """SELECT qa.booking_date, qa.queue_number, u.full_name, u.phone, qa.user_id
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
        date, num, name, phone, u_id = info

        if ADMIN_ID:
            admin_msg = (
                f"⚠️ Navbat bekor qilindi!\n\n"
                f"👤 Bemor: {name}\n"
                f"📞 Tel: {phone}\n"
                f"📅 Kun: Ertaga ({date})\n"
                f"🔢 Navbat raqami: {num}"
            )
            await bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown")


# --- ADMIN PANEL ---
@dp.message(F.text == "👨‍⚕️ Admin Panel")
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    conn = sqlite3.connect("dental_bot.db")
    cursor = conn.cursor()

    cursor.execute("""
                   SELECT qa.user_id, qa.booking_date, qa.queue_number, u.full_name, u.phone
                   FROM queue_appointments qa
                            JOIN users u ON u.user_id = qa.user_id
                   WHERE qa.booking_date = ?
                     AND qa.status = 'active'
                   ORDER BY qa.queue_number ASC
                   """, (tomorrow,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await message.answer("Ertaga uchun hech qanday navbatlar olinmagan.")
        return

    await message.answer("📋 Ertangi kun uchun olingan navbatlar (Vaqt yuborish uchun ustiga bosing):")

    for u_id, b_date, q_num, name, phone in rows:
        msg_text = f"📅 Ertaga | 🔢 {q_num}-navbat\n👤 {name}\n📞 {phone}"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⏱ 30 daqiqa", callback_data=f"notify_{u_id}_30 daqiqadan"),
                InlineKeyboardButton(text="⏱ 1 soat", callback_data=f"notify_{u_id}_1 soatdan")
            ],
            [
                InlineKeyboardButton(text="⏱ 2 soat", callback_data=f"notify_{u_id}_2 soatdan"),
                InlineKeyboardButton(text="🚨 Hozir kiring", callback_data=f"notify_{u_id}_hozir")
            ]
        ])
        await message.answer(msg_text, reply_markup=keyboard, parse_mode="Markdown")


# --- ADMIN BEMORGA XABAR YUBORISH HANDLERI ---
@dp.callback_query(F.data.startswith("notify_"))
async def send_time_notification(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    _, target_user_id, time_str = callback.data.split("_")
    target_user_id = int(target_user_id)

    try:
        if time_str == "hozir":
            user_msg = (
                "🚨 SIZNING NAVBATINGIZ KELDI!\n\n"
                "Iltimos, shifokor xonasiga kiring."
            )
        else:
            user_msg = (
                f"⏰ SHIFOKOR OGOHLANTIRISHI:\n\n"
                f"Sizning navbatingiz taxminan {time_str} keyin keladi.\n"
                f"Iltimos, klinikaga yetib keling yoki tayyor bo'lib turing!"
            )

        await bot.send_message(chat_id=target_user_id, text=user_msg, parse_mode="Markdown")
        await callback.answer(f"Xabar bemorga yuborildi! ({time_str})", show_alert=True)
    except Exception as e:
        await callback.answer("Xabar yuborishda xatolik! Bemor botni bloklagan bo'lishi mumkin.", show_alert=True)

# --- ISHGA TUSHIRISH ---
async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())