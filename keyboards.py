"""Barcha klaviaturalar shu yerda yig'ilgan."""

from datetime import timedelta

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from callbacks import (
    AdminCB,
    AdminDeptCB,
    AdminQueueCB,
    AdminSetCB,
    AdminUserCB,
    DateCB,
    DeptCB,
    NavCB,
    SlotCB,
    UserBookingCB,
)
import storage as db
from config import ADMIN_PAGE_SIZE, LIMITS, WEEKDAYS_UZ
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
    """Bo'limlar sozlamalardan o'qiladi — admin panelda o'zgartirsa darhol aks etadi."""
    kb = InlineKeyboardBuilder()
    for key, info in db.departments().items():
        kb.button(text=info["name"], callback_data=DeptCB(key=key))
    kb.adjust(1)
    return kb.as_markup()


def days(dept_key: str) -> InlineKeyboardMarkup:
    """Bugundan boshlab BOOKING_DAYS_AHEAD kun (dam olish kunlarisiz).

    Bugungi kun faqat hali bo'sh soat qolgan bo'lsa ko'rsatiladi.
    """
    kb = InlineKeyboardBuilder()
    times = db.dept_times(dept_key)
    today = now().date()
    days_ahead = db.rule("booking_days_ahead")
    weekend = set(db.rule("weekend_days") or [])
    lead = db.rule("min_lead_minutes")

    for offset in range(days_ahead + 1):
        day = today + timedelta(days=offset)
        if day.weekday() in weekend:
            continue

        date_str = day.strftime("%Y-%m-%d")
        if offset == 0 and not any(is_slot_bookable(date_str, t, lead) for t in times):
            continue  # bugun hamma soat o'tib ketgan

        prefix = "📅 Bugun" if offset == 0 else "📅 Ertaga" if offset == 1 else f"📅 {weekday_name(day)}"
        kb.button(text=f"{prefix} ({day.strftime('%d.%m')})", callback_data=DateCB(key=dept_key, date=date_str))

    kb.button(text="⬅️ Ortga (bo'limlar)", callback_data=NavCB(to="depts"))
    kb.adjust(1)
    return kb.as_markup()


def slots(dept_key: str, date_str: str, booked: set[str]) -> InlineKeyboardMarkup:
    """Soatlar: 🟢 bo'sh, ❌ band, ⌛ o'tib ketgan."""
    kb = InlineKeyboardBuilder()
    lead = db.rule("min_lead_minutes")
    for time_str in db.dept_times(dept_key):
        if time_str in booked:
            kb.button(text=f"❌ {time_str}", callback_data=NavCB(to="busy"))
        elif not is_slot_bookable(date_str, time_str, lead):
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
    """Admin menyusi.

    Oddiy admin faqat navbatlar bilan ishlaydi.
    Adminlarni boshqarish va parolni o'zgartirish tugmalari FAQAT super adminda
    ko'rinadi — oddiy adminda ular umuman chizilmaydi.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Navbatlar", callback_data=AdminCB(action="queue", page=0))
    kb.button(text="📊 Statistika", callback_data=AdminCB(action="stats"))

    if is_super:
        kb.button(text="⚙️ Sozlamalar", callback_data=AdminCB(action="settings"))
        kb.button(text="👥 Adminlar ro'yxati", callback_data=AdminCB(action="admins"))
        kb.button(text="🔑 Parolni o'zgartirish", callback_data=AdminCB(action="passwd"))
        kb.button(text="💾 Hozir zaxiralash", callback_data=AdminCB(action="backup"))
        kb.adjust(2, 2, 2)
    else:
        # Super admin o'zini chiqara olmaydi, shuning uchun unga bu tugma ham kerak emas
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


# --------------------------------------------------------------------------
# ⚙️ Sozlamalar (faqat super admin)
# --------------------------------------------------------------------------

def settings_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🏥 Bo'limlar va soatlar", callback_data=AdminCB(action="depts"))
    kb.button(text="📅 Navbat qoidalari", callback_data=AdminCB(action="rules"))
    kb.button(text="📍 Klinika ma'lumotlari", callback_data=AdminCB(action="clinic"))
    kb.button(text="🔔 Eslatmalar", callback_data=AdminCB(action="reminders"))
    kb.button(text="♻️ Standart holatga qaytarish", callback_data=AdminSetCB(action="reset_ask"))
    kb.button(text="⬅️ Admin menyusi", callback_data=AdminCB(action="menu"))
    kb.adjust(1)
    return kb.as_markup()


def back_to_settings() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Sozlamalar", callback_data=AdminCB(action="settings"))
    return kb.as_markup()


def departments_admin() -> InlineKeyboardMarkup:
    """Bo'limlar ro'yxati — har biri tahrirlash uchun bosiladi."""
    kb = InlineKeyboardBuilder()
    depts = db.departments()

    for key, info in depts.items():
        kb.row(InlineKeyboardButton(
            text=f"{info['name']} ({len(info['times'])} soat)",
            callback_data=AdminDeptCB(action="open", key=key).pack(),
        ))

    if len(depts) < LIMITS["max_departments"]:
        kb.row(InlineKeyboardButton(text="➕ Yangi bo'lim", callback_data=AdminDeptCB(action="add").pack()))
    kb.row(InlineKeyboardButton(text="⬅️ Sozlamalar", callback_data=AdminCB(action="settings").pack()))
    return kb.as_markup()


def department_edit(key: str, can_delete: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Nomini o'zgartirish", callback_data=AdminDeptCB(action="rename", key=key))
    kb.button(text="⏰ Soatlarini o'zgartirish", callback_data=AdminDeptCB(action="times", key=key))
    kb.button(text="🔼 Yuqoriga", callback_data=AdminDeptCB(action="up", key=key))
    kb.button(text="🔽 Pastga", callback_data=AdminDeptCB(action="down", key=key))
    if can_delete:
        kb.button(text="🗑 Bo'limni o'chirish", callback_data=AdminDeptCB(action="del_ask", key=key))
    kb.button(text="⬅️ Bo'limlar", callback_data=AdminCB(action="depts"))
    kb.adjust(1, 1, 2, 1, 1)
    return kb.as_markup()


def confirm_dept_delete(key: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha, o'chirilsin", callback_data=AdminDeptCB(action="del_yes", key=key))
    kb.button(text="🔙 Yo'q", callback_data=AdminDeptCB(action="open", key=key))
    kb.adjust(1)
    return kb.as_markup()


def rules_menu() -> InlineKeyboardMarkup:
    """Navbat qoidalari + dam olish kunlarini bir bosishda yoqish/o'chirish."""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text=f"📆 Oldindan: {db.rule('booking_days_ahead')} kun",
        callback_data=AdminSetCB(action="days").pack()))
    kb.row(InlineKeyboardButton(
        text=f"🔢 Bemorga limit: {db.rule('max_active_bookings')} ta",
        callback_data=AdminSetCB(action="max").pack()))
    kb.row(InlineKeyboardButton(
        text=f"⏱ Minimal vaqt: {db.rule('min_lead_minutes')} daqiqa",
        callback_data=AdminSetCB(action="lead").pack()))

    weekend = set(db.rule("weekend_days") or [])
    for start in (0, 4):
        kb.row(*[
            InlineKeyboardButton(
                text=f"{'🔴' if i in weekend else '🟢'} {WEEKDAYS_UZ[i][:3]}",
                callback_data=AdminSetCB(action="weekday", value=i).pack(),
            )
            for i in range(start, min(start + 4, 7))
        ])

    kb.row(InlineKeyboardButton(text="⬅️ Sozlamalar", callback_data=AdminCB(action="settings").pack()))
    return kb.as_markup()


def reminders_menu() -> InlineKeyboardMarkup:
    """Bemorga avtomatik eslatmalar."""
    r = db.reminders()
    hours = int(r.get("hours_before") or 0)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text=f"{'🟢' if r.get('day_before') else '🔴'} Kun oldin eslatish",
        callback_data=AdminSetCB(action="rem_day").pack()))
    kb.row(InlineKeyboardButton(
        text=f"⏰ Soat oldin: {hours if hours else 'o‘chiq'}",
        callback_data=AdminSetCB(action="rem_hours").pack()))
    kb.row(InlineKeyboardButton(text="⬅️ Sozlamalar", callback_data=AdminCB(action="settings").pack()))
    return kb.as_markup()


def clinic_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Manzilni o'zgartirish", callback_data=AdminSetCB(action="address"))
    kb.button(text="🗺 Xarita havolasini o'zgartirish", callback_data=AdminSetCB(action="maplink"))
    kb.button(text="⬅️ Sozlamalar", callback_data=AdminCB(action="settings"))
    kb.adjust(1)
    return kb.as_markup()


def confirm_reset() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha, standart holatga qaytar", callback_data=AdminSetCB(action="reset_yes"))
    kb.button(text="🔙 Yo'q", callback_data=AdminCB(action="settings"))
    kb.adjust(1)
    return kb.as_markup()
