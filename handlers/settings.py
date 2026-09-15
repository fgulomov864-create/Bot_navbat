"""⚙️ Sozlamalar — bo'limlar, ish soatlari, navbat qoidalari, klinika ma'lumotlari.

Hammasi FAQAT super adminga ochiq va hammasi `data.json` ichida saqlanadi.
Ya'ni ish soatlarini yoki manzilni o'zgartirish uchun kodga tegish va botni
qayta deploy qilish kerak emas — o'zgarish darhol kuchga kiradi.

Tugma chizilmasligi himoya emas (callback'ni qo'lda yuborish mumkin),
shuning uchun har bir handler `_super()` bilan boshlanadi.
"""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import keyboards as kb
import storage as db
from callbacks import AdminCB, AdminDeptCB, AdminSetCB
from config import LIMITS, WEEKDAYS_UZ
from services import edit_safe
from utils import esc, parse_times

log = logging.getLogger(__name__)
router = Router(name="settings")


class SettingsEdit(StatesGroup):
    """Bitta holat — nimani tahrirlash `state.update_data(what=...)` da saqlanadi."""
    waiting = State()


# --------------------------------------------------------------------------
# Yordamchilar
# --------------------------------------------------------------------------

async def _super(callback: CallbackQuery) -> bool:
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("⛔ Bu amal uchun ruxsatingiz yo'q.", show_alert=True)
        return False
    if not await db.is_super_admin(callback.from_user.id):
        await callback.answer("⛔ Sozlamalarni faqat super admin o'zgartira oladi.", show_alert=True)
        return False
    return True


async def _ask(callback: CallbackQuery, state: FSMContext, what: str, prompt: str, **extra) -> None:
    await state.set_state(SettingsEdit.waiting)
    await state.update_data(what=what, **extra)
    await edit_safe(callback.message, prompt + "\n\n<i>Bekor qilish uchun /cancel yuboring.</i>")
    await callback.answer()


def _reminders_short() -> str:
    r = db.reminders()
    parts = []
    if r.get("day_before"):
        parts.append("kun oldin")
    if int(r.get("hours_before") or 0):
        parts.append(f"{r['hours_before']} soat oldin")
    return ", ".join(parts) or "o'chiq"


def _settings_text() -> str:
    depts = db.departments()
    weekend = set(db.rule("weekend_days") or [])
    weekend_names = ", ".join(WEEKDAYS_UZ[i] for i in sorted(weekend)) or "yo'q"
    clinic = db.clinic()

    return (
        "⚙️ <b>Sozlamalar</b>\n\n"
        f"🏥 Bo'limlar: <b>{len(depts)}</b> ta "
        f"({sum(len(d['times']) for d in depts.values())} soat)\n"
        f"📆 Oldindan yozilish: <b>{db.rule('booking_days_ahead')}</b> kun\n"
        f"🔢 Bemorga limit: <b>{db.rule('max_active_bookings')}</b> ta navbat\n"
        f"⏱ Minimal vaqt: <b>{db.rule('min_lead_minutes')}</b> daqiqa\n"
        f"🔴 Dam olish: <b>{esc(weekend_names)}</b>\n"
        f"📍 Manzil: {esc(clinic.get('address'))}\n\n"
        "<i>Bu yerdagi hamma narsa botda darhol kuchga kiradi.</i>"
    )


async def _show_settings(callback: CallbackQuery) -> None:
    await edit_safe(callback.message, _settings_text(), reply_markup=kb.settings_menu())


async def _show_departments(callback: CallbackQuery) -> None:
    depts = db.departments()
    text = "🏥 <b>Bo'limlar va ish soatlari</b>\n\n"
    for i, (key, info) in enumerate(depts.items(), 1):
        text += (
            f"{i}. <b>{esc(info['name'])}</b>\n"
            f"   ⏰ {esc(', '.join(info['times'])) or '—'}\n"
            f"   🔖 <code>{esc(key)}</code>\n\n"
        )
    text += "<i>Tahrirlash uchun bo'lim nomini bosing.</i>"
    await edit_safe(callback.message, text, reply_markup=kb.departments_admin())


async def _show_department(callback: CallbackQuery, key: str) -> bool:
    info = db.department(key)
    if not info:
        await callback.answer("Bu bo'lim topilmadi.", show_alert=True)
        await _show_departments(callback)
        return False

    active = db.active_bookings_in_department(key)
    await edit_safe(
        callback.message,
        f"🏥 <b>{esc(info['name'])}</b>\n\n"
        f"⏰ Soatlar ({len(info['times'])} ta):\n{esc(', '.join(info['times'])) or '—'}\n\n"
        f"📋 Faol navbatlar: <b>{active}</b> ta",
        reply_markup=kb.department_edit(key, can_delete=len(db.departments()) > 1),
    )
    return True


# --------------------------------------------------------------------------
# Asosiy menyular
# --------------------------------------------------------------------------

@router.callback_query(AdminCB.filter(F.action == "settings"))
async def cb_settings(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _super(callback):
        return
    await state.clear()
    await _show_settings(callback)
    await callback.answer()


@router.callback_query(AdminCB.filter(F.action == "depts"))
async def cb_departments(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _super(callback):
        return
    await state.clear()
    await _show_departments(callback)
    await callback.answer()


@router.callback_query(AdminCB.filter(F.action == "rules"))
async def cb_rules(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _super(callback):
        return
    await state.clear()
    await edit_safe(
        callback.message,
        "📅 <b>Navbat qoidalari</b>\n\n"
        "📆 <b>Oldindan yozilish</b> — bemor necha kun oldin navbat ola oladi\n"
        "🔢 <b>Bemorga limit</b> — bir bemorda nechta faol navbat bo'lishi mumkin\n"
        "⏱ <b>Minimal vaqt</b> — qabulgacha kamida shuncha daqiqa qolishi shart\n\n"
        "Pastdagi kunlardan dam olish kunlarini belgilang "
        "(🔴 — yopiq, 🟢 — ishlaydi):",
        reply_markup=kb.rules_menu(),
    )
    await callback.answer()


@router.callback_query(AdminCB.filter(F.action == "clinic"))
async def cb_clinic(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _super(callback):
        return
    await state.clear()
    clinic = db.clinic()
    await edit_safe(
        callback.message,
        f"📍 <b>Klinika ma'lumotlari</b>\n\n"
        f"<b>Manzil:</b>\n{esc(clinic.get('address'))}\n\n"
        f"<b>Xarita havolasi:</b>\n{esc(clinic.get('map_link'))}\n\n"
        f"<i>Bemorlar «{kb.BTN_LOCATION}» tugmasini bosganda shu ko'rinadi.</i>",
        reply_markup=kb.clinic_menu(),
    )
    await callback.answer()


# --------------------------------------------------------------------------
# Bo'limlar
# --------------------------------------------------------------------------

@router.callback_query(AdminDeptCB.filter(F.action == "open"))
async def cb_dept_open(callback: CallbackQuery, callback_data: AdminDeptCB, state: FSMContext) -> None:
    if not await _super(callback):
        return
    await state.clear()
    await _show_department(callback, callback_data.key)
    await callback.answer()


@router.callback_query(AdminDeptCB.filter(F.action == "rename"))
async def cb_dept_rename(callback: CallbackQuery, callback_data: AdminDeptCB, state: FSMContext) -> None:
    if not await _super(callback):
        return
    info = db.department(callback_data.key)
    if not info:
        await callback.answer("Bu bo'lim topilmadi.", show_alert=True)
        return

    await _ask(
        callback, state, "dept_name",
        f"✏️ <b>Bo'lim nomini o'zgartirish</b>\n\n"
        f"Hozirgi nomi: <b>{esc(info['name'])}</b>\n\n"
        f"Yangi nomni yuboring (emoji ishlatish mumkin):",
        key=callback_data.key,
    )


@router.callback_query(AdminDeptCB.filter(F.action == "times"))
async def cb_dept_times(callback: CallbackQuery, callback_data: AdminDeptCB, state: FSMContext) -> None:
    if not await _super(callback):
        return
    info = db.department(callback_data.key)
    if not info:
        await callback.answer("Bu bo'lim topilmadi.", show_alert=True)
        return

    await _ask(
        callback, state, "dept_times",
        f"⏰ <b>«{esc(info['name'])}» ish soatlari</b>\n\n"
        f"Hozirgi: {esc(', '.join(info['times'])) or '—'}\n\n"
        f"Yangi soatlarni vergul bilan yuboring:\n"
        f"<code>09:00, 10:30, 12:00, 14:00</code>",
        key=callback_data.key,
    )


@router.callback_query(AdminDeptCB.filter(F.action == "add"))
async def cb_dept_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _super(callback):
        return
    if len(db.departments()) >= LIMITS["max_departments"]:
        await callback.answer(
            f"Bo'limlar soni {LIMITS['max_departments']} tadan oshmasligi kerak.", show_alert=True
        )
        return

    await _ask(
        callback, state, "new_dept_name",
        "➕ <b>Yangi bo'lim</b>\n\nBo'lim nomini yuboring:\n"
        "<code>🦷 Implantatsiya</code>",
    )


@router.callback_query(AdminDeptCB.filter(F.action.in_({"up", "down"})))
async def cb_dept_move(callback: CallbackQuery, callback_data: AdminDeptCB) -> None:
    if not await _super(callback):
        return

    keys = list(db.departments().keys())
    if callback_data.key not in keys:
        await callback.answer("Bu bo'lim topilmadi.", show_alert=True)
        return

    index = keys.index(callback_data.key)
    target = index - 1 if callback_data.action == "up" else index + 1
    if not 0 <= target < len(keys):
        await callback.answer("Bu bo'lim allaqachon chekkada.", show_alert=True)
        return

    keys[index], keys[target] = keys[target], keys[index]
    for order, key in enumerate(keys):
        await db.update_department_order(key, order)

    await _show_department(callback, callback_data.key)
    await callback.answer("Tartib o'zgartirildi")


@router.callback_query(AdminDeptCB.filter(F.action == "del_ask"))
async def cb_dept_delete_ask(callback: CallbackQuery, callback_data: AdminDeptCB) -> None:
    if not await _super(callback):
        return
    info = db.department(callback_data.key)
    if not info:
        await callback.answer("Bu bo'lim topilmadi.", show_alert=True)
        return

    active = db.active_bookings_in_department(callback_data.key)
    warning = (
        f"\n\n⚠️ Bu bo'limda <b>{active} ta faol navbat</b> bor! "
        f"Ular bekor qilinmaydi va admin panelida ko'rinib turadi, "
        f"lekin bemorlar bu bo'limga yangi yozila olmaydi."
        if active else ""
    )

    await edit_safe(
        callback.message,
        f"🗑 <b>Bo'limni o'chirasizmi?</b>\n\n<b>{esc(info['name'])}</b>{warning}",
        reply_markup=kb.confirm_dept_delete(callback_data.key),
    )
    await callback.answer()


@router.callback_query(AdminDeptCB.filter(F.action == "del_yes"))
async def cb_dept_delete(callback: CallbackQuery, callback_data: AdminDeptCB) -> None:
    if not await _super(callback):
        return

    if not await db.delete_department(callback_data.key):
        await callback.answer("O'chirib bo'lmadi — kamida bitta bo'lim qolishi kerak.", show_alert=True)
        await _show_departments(callback)
        return

    await callback.answer("🗑 Bo'lim o'chirildi")
    await _show_departments(callback)


# --------------------------------------------------------------------------
# Navbat qoidalari
# --------------------------------------------------------------------------

_RULE_PROMPTS = {
    "days": ("booking_days_ahead", "📆 <b>Oldindan yozilish</b>\n\nBemor necha kun oldin navbat ola olsin?"),
    "max": ("max_active_bookings", "🔢 <b>Bemorga limit</b>\n\nBir bemorda nechta faol navbat bo'lishi mumkin?"),
    "lead": ("min_lead_minutes", "⏱ <b>Minimal vaqt</b>\n\nQabulgacha kamida necha daqiqa qolishi shart?"),
}


@router.callback_query(AdminSetCB.filter(F.action.in_(set(_RULE_PROMPTS))))
async def cb_rule_ask(callback: CallbackQuery, callback_data: AdminSetCB, state: FSMContext) -> None:
    if not await _super(callback):
        return

    field, prompt = _RULE_PROMPTS[callback_data.action]
    low, high = LIMITS[field]
    await _ask(
        callback, state, "rule",
        f"{prompt}\n\nHozirgi qiymat: <b>{db.rule(field)}</b>\n"
        f"Ruxsat etilgan oraliq: <b>{low}…{high}</b>\n\nYangi sonni yuboring:",
        field=field,
    )


@router.callback_query(AdminSetCB.filter(F.action == "weekday"))
async def cb_weekday_toggle(callback: CallbackQuery, callback_data: AdminSetCB) -> None:
    if not await _super(callback):
        return

    day = callback_data.value
    if not 0 <= day <= 6:
        await callback.answer()
        return

    weekend = set(db.rule("weekend_days") or [])
    if day in weekend:
        weekend.discard(day)
        note = f"🟢 {WEEKDAYS_UZ[day]} — ish kuni"
    else:
        if len(weekend) >= 6:
            await callback.answer("Kamida bitta ish kuni qolishi kerak.", show_alert=True)
            return
        weekend.add(day)
        note = f"🔴 {WEEKDAYS_UZ[day]} — dam olish kuni"

    await db.set_rule("weekend_days", sorted(weekend))
    await callback.answer(note)
    await edit_safe(
        callback.message,
        "📅 <b>Navbat qoidalari</b>\n\n"
        "📆 <b>Oldindan yozilish</b> — bemor necha kun oldin navbat ola oladi\n"
        "🔢 <b>Bemorga limit</b> — bir bemorda nechta faol navbat bo'lishi mumkin\n"
        "⏱ <b>Minimal vaqt</b> — qabulgacha kamida shuncha daqiqa qolishi shart\n\n"
        "Pastdagi kunlardan dam olish kunlarini belgilang "
        "(🔴 — yopiq, 🟢 — ishlaydi):",
        reply_markup=kb.rules_menu(),
    )


# --------------------------------------------------------------------------
# 🔔 Eslatmalar
# --------------------------------------------------------------------------

def _reminders_text() -> str:
    r = db.reminders()
    hours = int(r.get("hours_before") or 0)
    day = "yoqilgan" if r.get("day_before") else "o'chiq"
    hour = f"{hours} soat" if hours else "o'chiq"
    return (
        "🔔 <b>Avtomatik eslatmalar</b>\n\n"
        "Bot bemorga qabul yaqinlashganda o'zi xabar beradi.\n\n"
        f"📅 Kun oldin: <b>{day}</b>\n"
        f"⏰ Soat oldin: <b>{hour}</b>\n\n"
        "<i>Kun oldingi eslatma qabulga 2 soatdan kam qolganda yuborilmaydi.</i>"
    )


@router.callback_query(AdminCB.filter(F.action == "reminders"))
async def cb_reminders(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _super(callback):
        return
    await state.clear()
    await edit_safe(callback.message, _reminders_text(), reply_markup=kb.reminders_menu())
    await callback.answer()


@router.callback_query(AdminSetCB.filter(F.action == "rem_day"))
async def cb_reminder_day(callback: CallbackQuery) -> None:
    if not await _super(callback):
        return
    new_value = not db.reminders().get("day_before")
    await db.set_reminder("day_before", new_value)
    await callback.answer("🟢 Yoqildi" if new_value else "🔴 O'chirildi")
    await edit_safe(callback.message, _reminders_text(), reply_markup=kb.reminders_menu())


@router.callback_query(AdminSetCB.filter(F.action == "rem_hours"))
async def cb_reminder_hours(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _super(callback):
        return
    low, high = LIMITS["hours_before"]
    await _ask(
        callback, state, "reminder_hours",
        f"⏰ <b>Qabuldan necha soat oldin eslatilsin?</b>\n\n"
        f"Hozirgi qiymat: <b>{db.reminders().get('hours_before', 0)}</b>\n"
        f"Ruxsat etilgan oraliq: <b>{low}…{high}</b> (0 = o'chirish)\n\n"
        f"Sonni yuboring:",
    )


# --------------------------------------------------------------------------
# Klinika ma'lumotlari
# --------------------------------------------------------------------------

@router.callback_query(AdminSetCB.filter(F.action == "address"))
async def cb_address(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _super(callback):
        return
    await _ask(
        callback, state, "clinic_address",
        f"📍 <b>Klinika manzili</b>\n\n"
        f"Hozirgi: {esc(db.clinic().get('address'))}\n\nYangi manzilni yuboring:",
    )


@router.callback_query(AdminSetCB.filter(F.action == "maplink"))
async def cb_maplink(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _super(callback):
        return
    await _ask(
        callback, state, "clinic_map",
        f"🗺 <b>Xarita havolasi</b>\n\n"
        f"Hozirgi: {esc(db.clinic().get('map_link'))}\n\n"
        f"Yangi havolani yuboring (https:// bilan boshlanishi kerak):",
    )


# --------------------------------------------------------------------------
# Standart holatga qaytarish
# --------------------------------------------------------------------------

@router.callback_query(AdminSetCB.filter(F.action == "reset_ask"))
async def cb_reset_ask(callback: CallbackQuery) -> None:
    if not await _super(callback):
        return
    await edit_safe(
        callback.message,
        "♻️ <b>Sozlamalarni standart holatga qaytarasizmi?</b>\n\n"
        "Bo'limlar, ish soatlari, navbat qoidalari va klinika ma'lumotlari\n"
        "boshlang'ich qiymatlarga qaytadi.\n\n"
        "✅ Bemorlar, navbatlar, adminlar va parol <b>tegilmaydi</b>.",
        reply_markup=kb.confirm_reset(),
    )
    await callback.answer()


@router.callback_query(AdminSetCB.filter(F.action == "reset_yes"))
async def cb_reset(callback: CallbackQuery) -> None:
    if not await _super(callback):
        return
    await db.reset_settings()
    log.info("Sozlamalar standart holatga qaytarildi (super admin: %s)", callback.from_user.id)
    await callback.answer("♻️ Sozlamalar tiklandi")
    await _show_settings(callback)


# --------------------------------------------------------------------------
# Matn kiritish — barcha tahrirlar shu yerga tushadi
# --------------------------------------------------------------------------

@router.message(
    SettingsEdit.waiting,
    F.text,
    ~Command("start", "cancel", "help", "admin"),
    ~F.text.in_(kb.MENU_BUTTONS),
)
async def on_value(message: Message, state: FSMContext) -> None:
    if not await db.is_super_admin(message.from_user.id):
        await state.clear()
        await message.answer("⛔ Sozlamalarni faqat super admin o'zgartira oladi.")
        return

    data = await state.get_data()
    what = data.get("what")
    value = message.text.strip()

    handler = {
        "dept_name": _save_dept_name,
        "dept_times": _save_dept_times,
        "new_dept_name": _save_new_dept_name,
        "new_dept_times": _save_new_dept_times,
        "rule": _save_rule,
        "reminder_hours": _save_reminder_hours,
        "clinic_address": _save_address,
        "clinic_map": _save_map,
    }.get(what)

    if handler is None:
        await state.clear()
        await message.answer("Amal bekor qilindi.", reply_markup=kb.main_menu(is_admin=True))
        return

    await handler(message, state, data, value)


async def _reopen_settings(message: Message, text: str) -> None:
    await message.answer(text)
    await message.answer(_settings_text(), reply_markup=kb.settings_menu())


async def _save_dept_name(message: Message, state: FSMContext, data: dict, value: str) -> None:
    low, high = LIMITS["dept_name_length"]
    if not low <= len(value) <= high:
        await message.answer(f"❌ Nom {low}–{high} belgidan iborat bo'lsin. Qayta yuboring:")
        return

    if not await db.update_department(data["key"], name=value):
        await state.clear()
        await message.answer("❌ Bu bo'lim endi mavjud emas.")
        return

    await state.clear()
    await _reopen_settings(message, f"✅ Bo'lim nomi o'zgartirildi: <b>{esc(value)}</b>")


async def _save_dept_times(message: Message, state: FSMContext, data: dict, value: str) -> None:
    times = parse_times(value)
    if times is None:
        await message.answer(
            "❌ Soatlarni tushunmadim.\n\n"
            "Namuna: <code>09:00, 10:30, 12:00</code>\nQayta yuboring:"
        )
        return

    low, high = LIMITS["dept_times_count"]
    if not low <= len(times) <= high:
        await message.answer(f"❌ Soatlar soni {low}–{high} orasida bo'lsin. Qayta yuboring:")
        return

    if not await db.update_department(data["key"], times=times):
        await state.clear()
        await message.answer("❌ Bu bo'lim endi mavjud emas.")
        return

    await state.clear()
    await _reopen_settings(
        message, f"✅ Ish soatlari yangilandi ({len(times)} ta):\n{esc(', '.join(times))}"
    )


async def _save_new_dept_name(message: Message, state: FSMContext, data: dict, value: str) -> None:
    low, high = LIMITS["dept_name_length"]
    if not low <= len(value) <= high:
        await message.answer(f"❌ Nom {low}–{high} belgidan iborat bo'lsin. Qayta yuboring:")
        return

    await state.update_data(what="new_dept_times", name=value)
    await message.answer(
        f"✅ Nomi: <b>{esc(value)}</b>\n\n"
        f"Endi ish soatlarini vergul bilan yuboring:\n"
        f"<code>09:00, 10:30, 12:00, 14:00</code>"
    )


async def _save_new_dept_times(message: Message, state: FSMContext, data: dict, value: str) -> None:
    times = parse_times(value)
    if times is None:
        await message.answer(
            "❌ Soatlarni tushunmadim.\n\n"
            "Namuna: <code>09:00, 10:30, 12:00</code>\nQayta yuboring:"
        )
        return

    low, high = LIMITS["dept_times_count"]
    if not low <= len(times) <= high:
        await message.answer(f"❌ Soatlar soni {low}–{high} orasida bo'lsin. Qayta yuboring:")
        return

    name = data.get("name", "Yangi bo'lim")
    await db.add_department(name, times)
    await state.clear()
    await _reopen_settings(
        message,
        f"✅ <b>Yangi bo'lim qo'shildi!</b>\n\n"
        f"🏥 {esc(name)}\n⏰ {esc(', '.join(times))}\n\n"
        f"Bemorlar uni «{kb.BTN_BOOK}» da darhol ko'radi.",
    )


async def _save_rule(message: Message, state: FSMContext, data: dict, value: str) -> None:
    field = data["field"]
    low, high = LIMITS[field]

    try:
        number = int(value)
    except ValueError:
        await message.answer(f"❌ Son kiriting ({low}…{high}). Qayta yuboring:")
        return

    if not low <= number <= high:
        await message.answer(f"❌ Qiymat {low}…{high} oralig'ida bo'lsin. Qayta yuboring:")
        return

    await db.set_rule(field, number)
    await state.clear()
    await _reopen_settings(message, f"✅ Saqlandi: <b>{number}</b>")


async def _save_reminder_hours(message: Message, state: FSMContext, data: dict, value: str) -> None:
    low, high = LIMITS["hours_before"]
    try:
        number = int(value)
    except ValueError:
        await message.answer(f"❌ Son kiriting ({low}…{high}). Qayta yuboring:")
        return
    if not low <= number <= high:
        await message.answer(f"❌ Qiymat {low}…{high} oralig'ida bo'lsin. Qayta yuboring:")
        return

    await db.set_reminder("hours_before", number)
    await state.clear()
    await _reopen_settings(
        message,
        f"✅ Saqlandi: {'eslatma o‘chirildi' if number == 0 else f'{number} soat oldin eslatiladi'}",
    )


async def _save_address(message: Message, state: FSMContext, data: dict, value: str) -> None:
    if len(value) < 3:
        await message.answer("❌ Manzil juda qisqa. Qayta yuboring:")
        return
    await db.set_clinic("address", value)
    await state.clear()
    await _reopen_settings(message, f"✅ Manzil yangilandi:\n{esc(value)}")


async def _save_map(message: Message, state: FSMContext, data: dict, value: str) -> None:
    if not value.startswith(("http://", "https://")):
        await message.answer(
            "❌ Havola <code>https://</code> bilan boshlanishi kerak. Qayta yuboring:"
        )
        return
    await db.set_clinic("map_link", value)
    await state.clear()
    await _reopen_settings(message, "✅ Xarita havolasi yangilandi.")
