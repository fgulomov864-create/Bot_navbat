"""Admin paneli: parol orqali kirish, navbatlarni boshqarish, adminlarni boshqarish.

Kirish tartibi:
  1. /admin -> parol so'raladi (boshlang'ich parol: config.DEFAULT_ADMIN_PASSWORD).
  2. To'g'ri parol kiritgan BIRINCHI odam SUPER ADMIN bo'ladi.
  3. Super admin parolni almashtira oladi va boshqa adminlarni ro'yxatdan chiqara oladi.
"""

import logging
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import storage as db
import keyboards as kb
from backup import backup
from callbacks import AdminCB, AdminQueueCB, AdminUserCB
from config import (
    ADMIN_PAGE_SIZE,
    DEFAULT_ADMIN_PASSWORD,
    LOGIN_BLOCK_MINUTES,
    LOGIN_MAX_ATTEMPTS,
    PASSWORD_MIN_LENGTH,
)
from services import booking_card, edit_safe, send_safe
from utils import esc, now

log = logging.getLogger(__name__)
router = Router(name="admin")

# Brute-force himoyasi (bot qayta ishga tushganda tozalanadi)
_attempts: dict[int, int] = {}
_blocked_until: dict[int, datetime] = {}


class AdminAuth(StatesGroup):
    waiting_password = State()


class AdminPassword(StatesGroup):
    waiting_new = State()


# --------------------------------------------------------------------------
# Yordamchilar
# --------------------------------------------------------------------------

def _fmt_ts(value: str | None) -> str:
    """ISO vaqtdan faqat sanani chiroyli ko'rinishda oladi."""
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value).strftime("%d.%m.%Y")
    except ValueError:
        return value[:10]


async def _deny(callback: CallbackQuery) -> None:
    """Ruxsatsiz bosishda tugma 'aylanib' qolmasligi uchun javob majburiy."""
    await callback.answer("⛔ Bu amal uchun ruxsatingiz yo'q.", show_alert=True)


async def _guard(callback: CallbackQuery, need_super: bool = False) -> bool:
    if not await db.is_admin(callback.from_user.id):
        await _deny(callback)
        return False
    if need_super and not await db.is_super_admin(callback.from_user.id):
        await callback.answer("⛔ Bu amalni faqat super admin bajara oladi.", show_alert=True)
        return False
    return True


async def _delete_quietly(message: Message) -> None:
    """Parol yozilgan xabarni chatdan olib tashlaydi."""
    try:
        await message.delete()
    except Exception:
        log.debug("Xabarni o'chirib bo'lmadi (chat_id=%s)", message.chat.id)


async def _panel_text(user_id: int) -> str:
    admin = await db.get_admin(user_id)
    is_super = bool(admin and admin["is_super"])
    counts = await db.stats()

    text = (
        f"👨‍⚕️ <b>Admin panel</b>\n\n"
        f"Sizning darajangiz: <b>{'👑 Super admin' if is_super else '👤 Admin'}</b>\n"
        f"📋 Kutilayotgan navbatlar: <b>{counts['upcoming']}</b>\n"
        f"📅 Bugunga: <b>{counts['today']}</b>\n"
    )
    # Adminlar soni va zaxira holati faqat super adminni qiziqtiradi
    if is_super:
        text += f"👥 Adminlar: <b>{counts['admins']}</b>\n{backup.status_line()}\n"

    return text + "\nKerakli bo'limni tanlang:"


async def open_panel(message: Message, user_id: int) -> None:
    is_super = await db.is_super_admin(user_id)
    await message.answer(await _panel_text(user_id), reply_markup=kb.admin_menu(is_super))


# --------------------------------------------------------------------------
# Kirish / parol
# --------------------------------------------------------------------------

@router.message(Command("admin"))
@router.message(F.text == kb.BTN_ADMIN)
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id

    if await db.is_admin(user_id):
        await open_panel(message, user_id)
        return

    blocked = _blocked_until.get(user_id)
    if blocked and blocked > now():
        left = int((blocked - now()).total_seconds() // 60) + 1
        await message.answer(f"⛔ Juda ko'p xato urinish. {left} daqiqadan keyin qayta urinib ko'ring.")
        return

    await state.set_state(AdminAuth.waiting_password)
    await message.answer(
        "🔐 <b>Admin paneliga kirish</b>\n\n"
        "Parolni yuboring (xabaringiz darhol o'chiriladi):",
        reply_markup=kb.cancel_input(),
    )


@router.message(
    AdminAuth.waiting_password,
    F.text,
    ~Command("start", "cancel", "help", "admin"),
    ~F.text.in_(kb.MENU_BUTTONS),
)
async def check_password(message: Message, state: FSMContext, bot: Bot) -> None:
    user_id = message.from_user.id
    entered = message.text.strip()
    await _delete_quietly(message)

    if not await db.verify_admin_password(entered):
        _attempts[user_id] = _attempts.get(user_id, 0) + 1
        left = LOGIN_MAX_ATTEMPTS - _attempts[user_id]

        if left <= 0:
            _blocked_until[user_id] = now() + timedelta(minutes=LOGIN_BLOCK_MINUTES)
            _attempts.pop(user_id, None)
            await state.clear()
            await message.answer(f"⛔ Parol {LOGIN_MAX_ATTEMPTS} marta xato kiritildi. "
                                 f"{LOGIN_BLOCK_MINUTES} daqiqaga bloklandingiz.")
            log.warning("Admin paneliga kirish bloklandi: user_id=%s", user_id)
            return

        await message.answer(f"❌ Parol noto'g'ri. Qolgan urinishlar: <b>{left}</b>")
        log.warning("Admin paroli xato kiritildi: user_id=%s", user_id)
        return

    # Parol to'g'ri
    _attempts.pop(user_id, None)
    _blocked_until.pop(user_id, None)
    await state.clear()

    became_super = await db.add_admin(
        user_id, message.from_user.full_name, message.from_user.username
    )

    if became_super:
        await message.answer(
            "✅ <b>Xush kelibsiz, super admin!</b>\n\n"
            "Siz panelga birinchi bo'lib kirdingiz, shuning uchun sizda to'liq huquq bor:\n"
            "• 🔑 parolni o'zgartirish\n"
            "• 👥 adminlarni ro'yxatdan chiqarish\n\n"
            "⚠️ <b>Birinchi navbatda parolni almashtiring!</b>",
            reply_markup=kb.main_menu(is_admin=True),
        )
        log.info("Super admin tayinlandi: user_id=%s", user_id)
    else:
        await message.answer(
            "✅ Siz admin sifatida qo'shildingiz.", reply_markup=kb.main_menu(is_admin=True)
        )
        log.info("Yangi admin qo'shildi: user_id=%s", user_id)
        await _notify_supers(bot, user_id, message.from_user.full_name, message.from_user.username)

    await open_panel(message, user_id)


async def _notify_supers(bot: Bot, new_id: int, full_name: str | None, username: str | None) -> None:
    text = (
        f"👥 <b>Panelga yangi admin kirdi</b>\n\n"
        f"👤 {esc(full_name)}" + (f" (@{esc(username)})" if username else "") + "\n"
        f"🆔 <code>{new_id}</code>\n\n"
        f"Agar bu siz tanimagan odam bo'lsa — parolni almashtiring va uni ro'yxatdan chiqaring."
    )
    for row in await db.list_admins():
        if row["is_super"] and row["user_id"] != new_id:
            await send_safe(bot, row["user_id"], text)


# --------------------------------------------------------------------------
# Panel menyusi
# --------------------------------------------------------------------------

@router.callback_query(AdminCB.filter(F.action == "menu"))
async def cb_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(callback):
        return
    await state.clear()
    is_super = await db.is_super_admin(callback.from_user.id)
    await edit_safe(callback.message, 
        await _panel_text(callback.from_user.id), reply_markup=kb.admin_menu(is_super)
    )
    await callback.answer()


@router.callback_query(AdminCB.filter(F.action == "stats"))
async def cb_stats(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    s = await db.stats()
    await edit_safe(callback.message, 
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Ro'yxatdan o'tgan bemorlar: <b>{s['users']}</b>\n"
        f"👨‍⚕️ Adminlar: <b>{s['admins']}</b>\n\n"
        f"📅 Bugungi navbatlar: <b>{s['today']}</b>\n"
        f"📋 Kutilayotgan navbatlar: <b>{s['upcoming']}</b>\n\n"
        f"<i>So'nggi 7 kun:</i>\n"
        f"✅ Qabul qilingan: <b>{s['done_week']}</b>\n"
        f"❌ Bekor qilingan: <b>{s['cancelled_week']}</b>\n\n"
        f"🗂 Jami yozuvlar: <b>{s['total']}</b>",
        reply_markup=kb.back_to_admin_menu(),
    )
    await callback.answer()


# --------------------------------------------------------------------------
# Navbatlar ro'yxati (sahifalangan)
# --------------------------------------------------------------------------

@router.callback_query(AdminCB.filter(F.action == "queue"))
async def cb_queue(callback: CallbackQuery, callback_data: AdminCB) -> None:
    if not await _guard(callback):
        return
    await _render_queue(callback, callback_data.page)
    await callback.answer()


async def _render_queue(callback: CallbackQuery, page: int) -> None:
    total = await db.count_upcoming_bookings()
    if total == 0:
        await edit_safe(callback.message, 
            "📋 <b>Navbatlar</b>\n\nHozircha kutilayotgan navbat yo'q.",
            reply_markup=kb.back_to_admin_menu(),
        )
        return

    page = max(0, min(page, (total - 1) // ADMIN_PAGE_SIZE))
    rows = await db.upcoming_bookings(ADMIN_PAGE_SIZE, page * ADMIN_PAGE_SIZE)

    text = f"📋 <b>Kutilayotgan navbatlar</b> — jami {total} ta\n\n"
    for row in rows:
        text += f"🔖 <b>#{row['id']}</b>\n{booking_card(row)}\n\n"
    text += "<i>🚨 chaqirish · ✅ keldi · 🚫 kelmadi · ❌ bekor qilish</i>"

    await edit_safe(callback.message, text, reply_markup=kb.admin_queue_page(rows, page, total))


@router.callback_query(AdminQueueCB.filter())
async def cb_queue_action(callback: CallbackQuery, callback_data: AdminQueueCB, bot: Bot) -> None:
    if not await _guard(callback):
        return

    booking = await db.get_booking(callback_data.id)
    if not booking or booking["status"] != "active":
        await callback.answer("Bu navbat allaqachon yopilgan.", show_alert=True)
        await _render_queue(callback, callback_data.page)
        return

    action = callback_data.action

    if action == "notify":
        sent = await send_safe(
            bot,
            booking["user_id"],
            "🚨 <b>SIZNING NAVBATINGIZ KELDI!</b>\n\n"
            + booking_card(booking, with_patient=False)
            + "\n\nShifokor sizni kutyapti, iltimos xonaga kiring.",
        )
        await callback.answer(
            "Bemorga xabar yuborildi ✅" if sent else "Xabar yetib bormadi — bemor botni bloklagan bo'lishi mumkin.",
            show_alert=True,
        )
        return

    labels = {"done": ("done", "✅ «Keldi» deb belgilandi"), "missed": ("missed", "🚫 «Kelmadi» deb belgilandi")}

    if action in labels:
        status, note = labels[action]
        await db.mark_booking(callback_data.id, status)
        await callback.answer(note)
    elif action == "cancel":
        await db.cancel_booking(callback_data.id)
        await callback.answer("❌ Navbat bekor qilindi")
        await send_safe(
            bot,
            booking["user_id"],
            "⚠️ <b>Navbatingiz klinika tomonidan bekor qilindi</b>\n\n"
            + booking_card(booking, with_patient=False)
            + "\n\nIltimos, boshqa vaqtga yoziling yoki klinikaga murojaat qiling.",
        )
    else:
        await callback.answer()
        return

    await _render_queue(callback, callback_data.page)


# --------------------------------------------------------------------------
# Qo'lda zaxiralash (faqat super admin)
# --------------------------------------------------------------------------

@router.callback_query(AdminCB.filter(F.action == "backup"))
async def cb_backup(callback: CallbackQuery) -> None:
    if not await _guard(callback, need_super=True):
        return

    if not backup.enabled:
        reason = f"\n\nSabab: {backup.last_error}" if backup.last_error else ""
        await callback.answer(
            "GitHub zaxirasi sozlanmagan.\n\n"
            "Railway'da BACKUP_REPO va BACKUP_TOKEN o'zgaruvchilarini qo'shing."
            f"{reason}",
            show_alert=True,
        )
        return

    await callback.answer("Yuborilmoqda…")
    ok = await backup.upload(force=True)
    await callback.answer(
        "💾 Zaxira GitHub'ga yuklandi" if ok
        else f"⚠️ Yuklanmadi: {backup.last_error or 'nomaʼlum xato'}",
        show_alert=True,
    )
    await edit_safe(
        callback.message,
        await _panel_text(callback.from_user.id),
        reply_markup=kb.admin_menu(is_super=True),
    )


# --------------------------------------------------------------------------
# Adminlar ro'yxati
# --------------------------------------------------------------------------

@router.callback_query(AdminCB.filter(F.action == "admins"))
async def cb_admins(callback: CallbackQuery) -> None:
    # Tugma oddiy adminda chizilmaydi, lekin callback'ni qo'lda yuborish mumkin —
    # shuning uchun serverda ham tekshiramiz
    if not await _guard(callback, need_super=True):
        return
    await _render_admins(callback)
    await callback.answer()


async def _render_admins(callback: CallbackQuery) -> None:
    rows = await db.list_admins()
    viewer_is_super = await db.is_super_admin(callback.from_user.id)

    text = f"👥 <b>Adminlar ro'yxati</b> — {len(rows)} ta\n\n"
    for i, row in enumerate(rows, 1):
        icon = "👑" if row["is_super"] else "👤"
        role = "Super admin" if row["is_super"] else "Admin"
        you = " ← <i>siz</i>" if row["user_id"] == callback.from_user.id else ""
        username = f" (@{esc(row['username'])})" if row["username"] else ""
        text += (
            f"{i}. {icon} <b>{esc(row['full_name'])}</b>{username}{you}\n"
            f"   🆔 <code>{row['user_id']}</code>\n"
            f"   📌 {role} · qo'shilgan: {_fmt_ts(row['added_at'])}\n\n"
        )

    if viewer_is_super:
        text += "<i>Super adminni ro'yxatdan chiqarib bo'lmaydi.</i>"
    else:
        text += "<i>Adminlarni faqat super admin boshqara oladi.</i>"

    await edit_safe(callback.message, text, reply_markup=kb.admins_list(rows, viewer_is_super))


@router.callback_query(AdminUserCB.filter(F.action == "del_ask"))
async def cb_remove_ask(callback: CallbackQuery, callback_data: AdminUserCB) -> None:
    if not await _guard(callback, need_super=True):
        return

    target = await db.get_admin(callback_data.user_id)
    if not target:
        await callback.answer("Bu admin ro'yxatda yo'q.", show_alert=True)
        await _render_admins(callback)
        return

    await edit_safe(callback.message, 
        f"❓ <b>Adminni ro'yxatdan chiqarasizmi?</b>\n\n"
        f"👤 {esc(target['full_name'])}\n"
        f"🆔 <code>{target['user_id']}</code>\n\n"
        f"U admin paneliga kira olmay qoladi. "
        f"Parolni bilsa — qayta kira oladi, shuning uchun parolni ham almashtiring.",
        reply_markup=kb.confirm_admin_removal(callback_data.user_id),
    )
    await callback.answer()


@router.callback_query(AdminUserCB.filter(F.action == "del_yes"))
async def cb_remove_apply(callback: CallbackQuery, callback_data: AdminUserCB, bot: Bot) -> None:
    if not await _guard(callback, need_super=True):
        return

    target = await db.get_admin(callback_data.user_id)
    if not await db.remove_admin(callback_data.user_id):
        await callback.answer("Chiqarib bo'lmadi (super adminni o'chirib bo'lmaydi).", show_alert=True)
        await _render_admins(callback)
        return

    log.info("Admin chiqarildi: %s (kim tomonidan: %s)", callback_data.user_id, callback.from_user.id)
    await callback.answer("✅ Admin ro'yxatdan chiqarildi")
    await _render_admins(callback)

    if target:
        await send_safe(
            bot,
            target["user_id"],
            "ℹ️ Siz admin ro'yxatidan chiqarildingiz. Admin paneli endi mavjud emas.",
            reply_markup=kb.main_menu(is_admin=False),
        )


# --------------------------------------------------------------------------
# Parolni o'zgartirish (faqat super admin)
# --------------------------------------------------------------------------

@router.callback_query(AdminCB.filter(F.action == "passwd"))
async def cb_password_ask(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(callback, need_super=True):
        return

    await state.set_state(AdminPassword.waiting_new)
    await edit_safe(callback.message, 
        f"🔑 <b>Yangi parolni yuboring</b>\n\n"
        f"• kamida {PASSWORD_MIN_LENGTH} ta belgi\n"
        f"• xabaringiz darhol o'chiriladi\n"
        f"• parol bazada ochiq saqlanmaydi (PBKDF2-SHA256)\n\n"
        f"Bekor qilish uchun /cancel yuboring.",
        reply_markup=None,
    )
    await callback.answer()


@router.message(
    AdminPassword.waiting_new,
    F.text,
    ~Command("start", "cancel", "help", "admin"),
    ~F.text.in_(kb.MENU_BUTTONS),
)
async def cb_password_set(message: Message, state: FSMContext, bot: Bot) -> None:
    new_password = message.text.strip()
    await _delete_quietly(message)

    if not await db.is_super_admin(message.from_user.id):
        await state.clear()
        await message.answer("⛔ Bu amalni faqat super admin bajara oladi.")
        return

    if len(new_password) < PASSWORD_MIN_LENGTH:
        await message.answer(f"❌ Parol kamida {PASSWORD_MIN_LENGTH} ta belgidan iborat bo'lsin. Qayta yuboring:")
        return

    if new_password == DEFAULT_ADMIN_PASSWORD:
        await message.answer("❌ Bu boshlang'ich parol — undan farqli parol tanlang:")
        return

    await db.change_admin_password(new_password)
    await state.clear()
    log.info("Admin paroli o'zgartirildi (super admin: %s)", message.from_user.id)

    await message.answer("✅ <b>Parol muvaffaqiyatli o'zgartirildi.</b>")
    await open_panel(message, message.from_user.id)

    # Boshqa adminlar eski parol endi ishlamasligini bilishlari kerak
    for row in await db.list_admins():
        if row["user_id"] != message.from_user.id:
            await send_safe(bot, row["user_id"], "ℹ️ Admin paneli paroli super admin tomonidan o'zgartirildi.")


# --------------------------------------------------------------------------
# Adminlikdan chiqish
# --------------------------------------------------------------------------

@router.callback_query(AdminCB.filter(F.action == "logout"))
async def cb_logout_ask(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return

    if await db.is_super_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Super admin o'zini ro'yxatdan chiqara olmaydi — aks holda parolni "
            "o'zgartiradigan odam qolmaydi.",
            show_alert=True,
        )
        return

    await edit_safe(callback.message, 
        "❓ <b>Admin huquqidan voz kechasizmi?</b>\n\n"
        "Panel yopiladi. Parolni bilsangiz, /admin orqali qayta kirishingiz mumkin.",
        reply_markup=kb.confirm_logout(),
    )
    await callback.answer()


@router.callback_query(AdminCB.filter(F.action == "logout_yes"))
async def cb_logout_apply(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return

    if not await db.remove_admin(callback.from_user.id):
        await callback.answer("⛔ Super admin o'zini chiqara olmaydi.", show_alert=True)
        return

    await edit_safe(callback.message, "✅ Siz admin ro'yxatidan chiqdingiz.")
    await callback.message.answer("🏠 Bosh menyu:", reply_markup=kb.main_menu(is_admin=False))
    await callback.answer()
