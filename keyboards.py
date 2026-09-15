"""Barcha klaviaturalar shu yerda yig'ilgan."""

from datetime import timedelta

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from callbacks import AdminCB, AdminQueueCB, AdminUserCB, DateCB, DeptCB, NavCB, SlotCB, UserBookingCB
from config import ADMIN_PAGE_SIZE, BOOKING_DAYS_AHEAD, DEPARTMENTS, WEEKEND_DAYS
from utils import is_slot_bookable, now, to_date, weekday_name

BTN_BOOK = "📅 Navbat olish"
BTN_MY = "📋 Mening navbatim"
BTN_CANCEL = "❌ Navbatni bekor qilish"
BTN_LOCATION = "📍 Manzil / Lokatsiya"
BTN_ADMIN = "👨‍⚕️ Admin panel"

# Foydalanuvchi biror ma'lumot kiritayotgan paytda (telefon, parol) menyu tugmasini bossa,
# uni "kiritilgan matn" deb hisoblamaslik kerak — aks holda odam holatda qamalib qoladi.
MENU_BUTTONS = frozenset({BTN_BOOK, BTN_MY, BTN_CANCEL, BTN_LOCATION, BTN_ADMIN})


# --------------------------------------------------------------------------
# Reply klaviaturalar
# --------------------------------------------------------------------------

def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BTN_BOOK)],
        [KeyboardButton(text=BTN_MY), KeyboardButton(text=BTN_CANCEL)],
        [KeyboardButton(text=BTN_LOCATION)],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=BTN_ADMIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def phone_request() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Yoki raqamni qo'lda yozing: +998901234567",
    )


# --------------------------------------------------------------------------
# Navbat olish jarayoni
# --------------------------------------------------------------------------

def departments() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, info in DEPARTMENTS.items():
        kb.button(text=info["name"], callback_data=DeptCB(key=key))
    kb.adjust(1)
    return kb.as_markup()


def days(dept_key: str) -> InlineKeyboardMarkup:
    """Bugundan boshlab BOOKING_DAYS_AHEAD kun (dam olish kunlarisiz).

    Bugungi kun faqat hali bo'sh soat qolgan bo'lsa ko'rsatiladi.
    """
    kb = InlineKeyboardBuilder()
    times = DEPARTMENTS.get(dept_key, {}).get("times", [])
    today = now().date()

    for offset in range(BOOKING_DAYS_AHEAD + 1):
        day = today + timedelta(days=offset)
        if day.weekday() in WEEKEND_DAYS:
            continue

        date_str = day.strftime("%Y-%m-%d")
        if offset == 0 and not any(is_slot_bookable(date_str, t) for t in times):
            continue  # bugun hamma soat o'tib ketgan

        prefix = "📅 Bugun" if offset == 0 else "📅 Ertaga" if offset == 1 else f"📅 {weekday_name(day)}"
        kb.button(text=f"{prefix} ({day.strftime('%d.%m')})", callback_data=DateCB(key=dept_key, date=date_str))

    kb.button(text="⬅️ Ortga (bo'limlar)", callback_data=NavCB(to="depts"))
    kb.adjust(1)
    return kb.as_markup()


def slots(dept_key: str, date_str: str, booked: set[str]) -> InlineKeyboardMarkup:
    """Soatlar: 🟢 bo'sh, ❌ band, ⌛ o'tib ketgan."""
    kb = InlineKeyboardBuilder()
    for time_str in DEPARTMENTS.get(dept_key, {}).get("times", []):
        if time_str in booked:
            kb.button(text=f"❌ {time_str}", callback_data=NavCB(to="busy"))
        elif not is_slot_bookable(date_str, time_str):
            kb.button(text=f"⌛ {time_str}", callback_data=NavCB(to="past"))
        else:
            kb.button(text=f"🟢 {time_str}", callback_data=SlotCB(key=dept_key, date=date_str, time=time_str))
    kb.adjust(2)
    kb.row(InlineKeyboardButton(text="⬅️ Ortga (kunlar)", callback_data=DeptCB(key=dept_key).pack()))
    return kb.as_markup()


def my_bookings_cancel(rows: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for row in rows:
        kb.button(
            text=f"❌ {to_date(row['booking_date']).strftime('%d.%m')} {row['booking_time']} — {row['service_name']}",
            callback_data=UserBookingCB(action="ask", id=row["id"]),
        )
    kb.button(text="🔙 Yopish", callback_data=NavCB(to="close"))
    kb.adjust(1)
    return kb.as_markup()


def confirm_user_cancel(app_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha, bekor qilinsin", callback_data=UserBookingCB(action="yes", id=app_id))
    kb.button(text="🔙 Yo'q", callback_data=NavCB(to="close"))
    kb.adjust(1)
    return kb.as_markup()


# --------------------------------------------------------------------------
# Admin panel
# --------------------------------------------------------------------------

def admin_menu(is_super: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Navbatlar", callback_data=AdminCB(action="queue", page=0))
    kb.button(text="📊 Statistika", callback_data=AdminCB(action="stats"))
    kb.button(text="👥 Adminlar ro'yxati", callback_data=AdminCB(action="admins"))
    if is_super:
        kb.button(text="🔑 Parolni o'zgartirish", callback_data=AdminCB(action="passwd"))
    kb.button(text="🚪 Adminlikdan chiqish", callback_data=AdminCB(action="logout"))
    kb.adjust(2, 1)
    return kb.as_markup()


def back_to_admin_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Admin menyusi", callback_data=AdminCB(action="menu"))
    return kb.as_markup()


def admin_queue_page(rows: list[dict], page: int, total: int) -> InlineKeyboardMarkup:
    """Har bir navbat uchun bitta qator tugmalar + sahifalash."""
    kb = InlineKeyboardBuilder()
    for row in rows:
        label = f"{to_date(row['booking_date']).strftime('%d.%m')} {row['booking_time']}"
        kb.row(
            InlineKeyboardButton(text=f"🚨 {label}", callback_data=AdminQueueCB(action="notify", id=row["id"], page=page).pack()),
            InlineKeyboardButton(text="✅", callback_data=AdminQueueCB(action="done", id=row["id"], page=page).pack()),
            InlineKeyboardButton(text="🚫", callback_data=AdminQueueCB(action="missed", id=row["id"], page=page).pack()),
            InlineKeyboardButton(text="❌", callback_data=AdminQueueCB(action="cancel", id=row["id"], page=page).pack()),
        )

    last_page = max(0, (total - 1) // ADMIN_PAGE_SIZE)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=AdminCB(action="queue", page=page - 1).pack()))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{last_page + 1}", callback_data=NavCB(to="noop").pack()))
    if page < last_page:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=AdminCB(action="queue", page=page + 1).pack()))
    if len(nav) > 1:
        kb.row(*nav)

    kb.row(InlineKeyboardButton(text="⬅️ Admin menyusi", callback_data=AdminCB(action="menu").pack()))
    return kb.as_markup()


def admins_list(rows: list[dict], viewer_is_super: bool) -> InlineKeyboardMarkup:
    """Adminlar ro'yxati. Super admin har bir oddiy adminni o'chira oladi."""
    kb = InlineKeyboardBuilder()
    if viewer_is_super:
        for row in rows:
            if row["is_super"]:
                continue  # super adminni o'chirib bo'lmaydi
            name = row["full_name"] or str(row["user_id"])
            kb.row(
                InlineKeyboardButton(
                    text=f"❌ {name} ni chiqarish",
                    callback_data=AdminUserCB(action="del_ask", user_id=row["user_id"]).pack(),
                )
            )
    kb.row(InlineKeyboardButton(text="⬅️ Admin menyusi", callback_data=AdminCB(action="menu").pack()))
    return kb.as_markup()


def confirm_admin_removal(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha, chiqarilsin", callback_data=AdminUserCB(action="del_yes", user_id=user_id))
    kb.button(text="🔙 Bekor qilish", callback_data=AdminCB(action="admins"))
    kb.adjust(1)
    return kb.as_markup()


def confirm_logout() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha, chiqaman", callback_data=AdminCB(action="logout_yes"))
    kb.button(text="🔙 Yo'q", callback_data=AdminCB(action="menu"))
    kb.adjust(1)
    return kb.as_markup()


def cancel_input() -> InlineKeyboardMarkup:
    """Parol kiritish jarayonini bekor qilish."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Bekor qilish", callback_data=NavCB(to="close"))
    return kb.as_markup()
