"""Ro'yxatdan o'tish, bosh menyu, manzil."""

import logging
import re

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import storage as db
import keyboards as kb
from callbacks import NavCB
from config import CLINIC_ADDRESS, MAP_LINK
from utils import esc

log = logging.getLogger(__name__)
router = Router(name="common")

# +998901234567 / 998901234567 / 901234567 — bo'sh joy, tire, qavslarga ruxsat
PHONE_RE = re.compile(r"^\+?(?:998)?(\d{9})$")


class Registration(StatesGroup):
    waiting_phone = State()


def normalize_phone(raw: str) -> str | None:
    """Turli formatdagi raqamni '+998XXXXXXXXX' ko'rinishiga keltiradi."""
    cleaned = re.sub(r"[\s\-()]", "", raw or "")
    match = PHONE_RE.match(cleaned)
    return f"+998{match.group(1)}" if match else None


async def show_main_menu(message: Message, text: str = "🏠 Bosh menyu:") -> None:
    is_admin = await db.is_admin(message.from_user.id)
    await message.answer(text, reply_markup=kb.main_menu(is_admin))


async def ask_phone(message: Message, state: FSMContext) -> None:
    await state.set_state(Registration.waiting_phone)
    await message.answer(
        "📱 Navbat olish uchun avval telefon raqamingiz kerak.\n\n"
        "Pastdagi tugmani bosing yoki raqamni qo'lda yozing:\n"
        "<code>+998901234567</code>",
        reply_markup=kb.phone_request(),
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()

    if await db.is_registered(message.from_user.id):
        await show_main_menu(
            message,
            f"Assalomu alaykum, {esc(message.from_user.first_name)}! 👋\n"
            f"Quyidagi menyudan kerakli bo'limni tanlang:",
        )
    else:
        await message.answer(
            f"Assalomu alaykum, {esc(message.from_user.first_name)}! 👋\n"
            f"Stomatolog qabuliga yozilish botiga xush kelibsiz."
        )
        await ask_phone(message, state)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await show_main_menu(message)
        return
    await state.clear()
    await show_main_menu(message, "✅ Amal bekor qilindi.")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "ℹ️ <b>Bot imkoniyatlari</b>\n\n"
        f"{kb.BTN_BOOK} — bo'lim, kun va soatni tanlab navbat olish\n"
        f"{kb.BTN_MY} — faol navbatlaringizni ko'rish\n"
        f"{kb.BTN_CANCEL} — navbatni bekor qilish\n"
        f"{kb.BTN_LOCATION} — klinika manzili\n\n"
        "<b>Komandalar:</b>\n"
        "/start — botni qayta ishga tushirish\n"
        "/cancel — joriy amaldan chiqish\n"
        "/help — shu yordam\n"
        "/admin — admin paneli (parol bilan)"
    )


@router.message(F.contact)
async def on_contact(message: Message, state: FSMContext) -> None:
    contact = message.contact

    # Boshqa odamning kontaktini yuborib ro'yxatdan o'tib bo'lmaydi
    if contact.user_id != message.from_user.id:
        await message.answer(
            "⚠️ Iltimos, <b>o'zingizning</b> raqamingizni yuboring "
            "(pastdagi tugma orqali).",
            reply_markup=kb.phone_request(),
        )
        return

    phone = normalize_phone(contact.phone_number) or contact.phone_number
    await db.save_user(message.from_user.id, message.from_user.full_name, message.from_user.username, phone)
    await state.clear()
    await show_main_menu(message, f"✅ Raqamingiz saqlandi: <b>{esc(phone)}</b>")


@router.message(
    Registration.waiting_phone,
    F.text,
    ~Command("start", "cancel", "help", "admin"),
    ~F.text.in_(kb.MENU_BUTTONS),
)
async def on_manual_phone(message: Message, state: FSMContext) -> None:
    phone = normalize_phone(message.text)
    if not phone:
        await message.answer(
            "❌ Raqam noto'g'ri kiritildi.\n\n"
            "Namuna: <code>+998901234567</code>\n"
            "Yoki pastdagi tugmadan foydalaning.",
            reply_markup=kb.phone_request(),
        )
        return

    await db.save_user(message.from_user.id, message.from_user.full_name, message.from_user.username, phone)
    await state.clear()
    await show_main_menu(message, f"✅ Raqamingiz saqlandi: <b>{esc(phone)}</b>")


@router.message(F.text == kb.BTN_LOCATION)
async def on_location(message: Message) -> None:
    await message.answer(
        f"📍 <b>Bizning manzilimiz</b>\n\n"
        f"{esc(CLINIC_ADDRESS)}\n\n"
        f'🔗 <a href="{MAP_LINK}">Google Maps orqali ochish</a>',
        disable_web_page_preview=False,
    )


@router.callback_query(NavCB.filter(F.to == "close"))
async def on_close(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("✅ Yopildi.")
    await callback.answer()


@router.callback_query(NavCB.filter(F.to == "busy"))
async def on_busy_slot(callback: CallbackQuery) -> None:
    await callback.answer("Bu soat allaqachon band qilingan.", show_alert=True)


@router.callback_query(NavCB.filter(F.to == "past"))
async def on_past_slot(callback: CallbackQuery) -> None:
    await callback.answer("Bu vaqt o'tib ketgan.", show_alert=True)


@router.callback_query(NavCB.filter(F.to == "noop"))
async def on_noop(callback: CallbackQuery) -> None:
    await callback.answer()
