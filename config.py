"""Bot sozlamalari — barcha maxfiy ma'lumotlar .env faylidan o'qiladi."""

import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# .env ni har doim loyiha papkasidan o'qiymiz (bot qayerdan ishga tushirilishidan qat'i nazar)
load_dotenv(BASE_DIR / ".env")


def _require(key: str) -> str:
    value = (os.getenv(key) or "").strip()
    if not value:
        raise RuntimeError(
            f"❌ .env faylida '{key}' topilmadi.\n"
            f"   .env.example faylidan nusxa oling: cp .env.example .env"
        )
    return value


# --- Majburiy sozlamalar ---
BOT_TOKEN: str = _require("BOT_TOKEN")

# --- Ixtiyoriy sozlamalar ---
# ADMIN_ID berilsa, o'sha foydalanuvchi avtomatik super admin bo'ladi.
# Berilmasa — parolni birinchi bo'lib to'g'ri kiritgan odam super admin bo'ladi.
_raw_admin_id = (os.getenv("ADMIN_ID") or "").strip()
try:
    ADMIN_ID: int | None = int(_raw_admin_id) if _raw_admin_id else None
except ValueError:
    raise RuntimeError(f"❌ .env dagi ADMIN_ID butun son bo'lishi kerak, olindi: {_raw_admin_id!r}")

TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Asia/Tashkent"))

# Ma'lumotlar JSON faylida saqlanadi (ilgari SQLite ishlatilgan).
# Yo'l absolyut — bot boshqa papkadan ishga tushirilsa ham o'sha bazani topadi.
DATA_PATH = BASE_DIR / (os.getenv("DATA_FILE") or "data.json")

# Eski SQLite bazasi — faqat migrate_to_json.py uchun kerak
LEGACY_DB_PATH = BASE_DIR / (os.getenv("LEGACY_DB") or "dental_bot.db")
MAP_LINK = os.getenv("MAP_LINK", "https://maps.app.goo.gl/Ay8YVsm44MMAWxst9?g_st=ac")
CLINIC_ADDRESS = os.getenv("CLINIC_ADDRESS", "Stomatologiya klinikasi")

# --- Admin paneliga kirish ---
# Bu faqat BOSHLANG'ICH parol. Birinchi kirgan super admin uni panel orqali o'zgartiradi.
# Baza ichida ochiq emas, PBKDF2-SHA256 hash ko'rinishida saqlanadi.
DEFAULT_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1234567890")
PASSWORD_MIN_LENGTH = 4
LOGIN_MAX_ATTEMPTS = 5  # necha marta xato kiritgach bloklanadi
LOGIN_BLOCK_MINUTES = 15  # blok muddati

# --- Navbat qoidalari ---
BOOKING_DAYS_AHEAD = 7  # necha kun oldindan navbat olish mumkin
MAX_ACTIVE_BOOKINGS = 3  # bir foydalanuvchidagi faol navbatlar limiti
MIN_LEAD_MINUTES = 30  # bugungi kunga: qabulgacha kamida shuncha daqiqa qolishi shart
WEEKEND_DAYS = {6}  # 0=Dushanba ... 6=Yakshanba
ADMIN_PAGE_SIZE = 5  # admin panelida bir sahifadagi navbatlar soni

DEPARTMENTS: dict[str, dict] = {
    "treatment": {
        "name": "🦷 Davolash bo'limi",
        "times": ["09:00", "10:30", "12:00", "13:30", "15:00", "16:30", "18:00"],
    },
    "consultation": {
        "name": "👨‍⚕️ Maslahat olish",
        "times": ["09:30", "11:00", "12:30", "14:00", "15:30", "17:00", "18:30"],
    },
}

WEEKDAYS_UZ = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]


def dept_name(dept_key: str) -> str:
    """Bo'lim kalitidan uning nomini qaytaradi (noma'lum kalit uchun ham xavfsiz)."""
    return DEPARTMENTS.get(dept_key, {}).get("name", "🦷 Davolash bo'limi")
