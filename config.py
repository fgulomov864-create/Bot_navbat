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

def _parse_ids(raw: str) -> list[int]:
    """Bir nechta ID ni turli formatda qabul qiladi.

    Hammasi ishlaydi:
        ADMIN_ID=                   -> []
        ADMIN_ID=[]                 -> []
        ADMIN_ID=637554472          -> [637554472]
        ADMIN_ID=[637554472, 123]   -> [637554472, 123]
        ADMIN_ID=637554472,123      -> [637554472, 123]
        ADMIN_ID=637554472 123      -> [637554472, 123]
    """
    cleaned = (raw or "").strip().strip("[]()")
    parts = [p.strip().strip("'\"") for p in cleaned.replace(",", " ").split()]

    ids: list[int] = []
    for part in parts:
        if not part:
            continue
        try:
            value = int(part)
        except ValueError:
            raise RuntimeError(
                f"❌ .env dagi ADMIN_ID butun sonlardan iborat bo'lishi kerak.\n"
                f"   Tushunarsiz qiymat: {part!r}\n"
                f"   Namuna: ADMIN_ID=[637554472, 123456789]"
            )
        if value not in ids:
            ids.append(value)
    return ids


# ADMIN_ID da ko'rsatilgan HAR BIR foydalanuvchi avtomatik super admin bo'ladi.
# Bo'sh qoldirilsa — parolni birinchi bo'lib to'g'ri kiritgan odam super admin bo'ladi.
ADMIN_IDS: list[int] = _parse_ids(os.getenv("ADMIN_IDS") or os.getenv("ADMIN_ID") or "")

TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Asia/Tashkent"))

# Ma'lumotlar JSON faylida saqlanadi.
# Nisbiy yo'l loyiha papkasiga nisbatan, absolyut yo'l (masalan Railway'dagi
# /data/data.json) o'zgarishsiz ishlatiladi.
_raw_data_file = os.getenv("DATA_FILE") or "data.json"
DATA_PATH = Path(_raw_data_file) if Path(_raw_data_file).is_absolute() else BASE_DIR / _raw_data_file

# --- Admin paneliga kirish ---
# Bu faqat BOSHLANG'ICH parol. Birinchi kirgan super admin uni panel orqali o'zgartiradi.
# Baza ichida ochiq emas, PBKDF2-SHA256 hash ko'rinishida saqlanadi.
DEFAULT_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1234567890")
PASSWORD_MIN_LENGTH = 4
LOGIN_MAX_ATTEMPTS = 5  # necha marta xato kiritgach bloklanadi
LOGIN_BLOCK_MINUTES = 15  # blok muddati

# --- Kod darajasidagi konstantalar (panel orqali o'zgartirilmaydi) ---
ADMIN_PAGE_SIZE = 5  # admin panelida bir sahifadagi navbatlar soni

# ==========================================================================
# QUYIDAGILAR FAQAT BOSHLANG'ICH QIYMATLAR
#
# Bot birinchi marta ishga tushganda ular data.json ichiga ko'chiriladi va
# undan keyin super admin ularni PANEL orqali o'zgartiradi (⚙️ Sozlamalar).
# Ya'ni ish soatlarini yoki manzilni o'zgartirish uchun kodga tegish shart emas.
# ==========================================================================

DEFAULT_DEPARTMENTS: dict[str, dict] = {
    "treatment": {
        "name": "🦷 Davolash bo'limi",
        "times": ["09:00", "10:30", "12:00", "13:30", "15:00", "16:30", "18:00"],
    },
    "consultation": {
        "name": "👨‍⚕️ Maslahat olish",
        "times": ["09:30", "11:00", "12:30", "14:00", "15:30", "17:00", "18:30"],
    },
}

DEFAULT_RULES: dict[str, object] = {
    "booking_days_ahead": 7,   # necha kun oldindan navbat olish mumkin
    "max_active_bookings": 3,  # bir bemordagi faol navbatlar limiti
    "min_lead_minutes": 30,    # bugungi kunga: qabulgacha kamida shuncha daqiqa
    "weekend_days": [6],       # 0=Dushanba ... 6=Yakshanba
}

DEFAULT_CLINIC: dict[str, str] = {
    "address": os.getenv("CLINIC_ADDRESS", "Stomatologiya klinikasi"),
    "map_link": os.getenv("MAP_LINK", "https://maps.app.goo.gl/Ay8YVsm44MMAWxst9?g_st=ac"),
}

# Sozlamalar uchun chegaralar — panelda tekshiriladi
LIMITS = {
    "booking_days_ahead": (1, 30),
    "max_active_bookings": (1, 20),
    "min_lead_minutes": (0, 1440),
    "dept_name_length": (2, 64),
    "dept_times_count": (1, 24),
    "max_departments": 12,
}

WEEKDAYS_UZ = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]

# --- GitHub'ga zaxiralash (Railway va shunga o'xshash platformalar uchun) ---
# Railway'da konteyner diski VAQTINCHALIK: har bir redeploy'da data.json yo'qoladi.
# Ikkita yechim bor va ularni birga ishlatish mumkin:
#   1) Railway Volume — /data ga ulanadi, DATA_FILE=/data/data.json (ASOSIY yechim);
#   2) quyidagi GitHub zaxirasi — fayl davriy ravishda repozitoriyga yuklanadi va
#      bot ishga tushganda baza bo'sh bo'lsa, o'sha yerdan tiklanadi.
#
# ⚠️ Zaxira repozitoriyasi FAQAT private bo'lishi mumkin — ichida bemorlarning
#    ismi va telefon raqami bo'ladi. Bot public repo'ga yozishdan bosh tortadi.
BACKUP_REPO = (os.getenv("BACKUP_REPO") or "").strip()          # "foydalanuvchi/repo"
BACKUP_TOKEN = (os.getenv("BACKUP_TOKEN") or "").strip()        # GitHub Personal Access Token
BACKUP_BRANCH = (os.getenv("BACKUP_BRANCH") or "main").strip()
BACKUP_FILE = (os.getenv("BACKUP_FILE") or "backup/data.json").strip()
BACKUP_INTERVAL_MINUTES = int(os.getenv("BACKUP_INTERVAL_MINUTES") or 5)

BACKUP_ENABLED = bool(BACKUP_REPO and BACKUP_TOKEN)
