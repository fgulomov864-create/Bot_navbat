"""JSON asosidagi ma'lumotlar qatlami (SQLite o'rnini bosadi).

Ishlash prinsipi
----------------
Butun baza bitta `data.json` faylida turadi va bot ishga tushganda
TO'LIQ operativ xotiraga yuklanadi. Shu sababli barcha o'qish amallari
diskka murojaat qilmaydi — ular oddiy dict/list amallari.

Tezlik uchun 3 ta indeks yuritiladi (SQLite indekslarining o'rnini bosadi):
  _by_id    : id            -> navbat            (O(1) qidiruv)
  _by_user  : user_id       -> navbatlar ro'yxati (O(1) filtrlash)
  _by_slot  : (bo'lim, kun, soat) -> navbat id    (O(1) bandlik tekshiruvi)

Ma'lumot butunligi
------------------
* Har bir o'zgartirish `asyncio.Lock` ichida bajariladi — ikki foydalanuvchi
  bir vaqtda yozganda ham fayl buzilmaydi.
* Yozish ATOMAR: avval `data.json.tmp` ga yoziladi, keyin `os.replace` bilan
  almashtiriladi. Jarayon o'rtada uzilsa ham eski fayl butun qoladi.
* Har safar saqlashdan oldin `data.json.bak` nusxasi yangilanadi.

Tashqi ma'lumotlar bazasi (SQLite, PostgreSQL) kerak emas — faqat standart kutubxona.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

from config import (
    DATA_PATH,
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_CLINIC,
    DEFAULT_DEPARTMENTS,
    DEFAULT_REMINDERS,
    DEFAULT_RULES,
)
from utils import now

log = logging.getLogger(__name__)

SCHEMA_VERSION = 2
PBKDF2_ROUNDS = 200_000

ACTIVE = "active"
CANCELLED = "cancelled"
DONE = "done"
MISSED = "missed"

# --- Xotiradagi holat ---
_data: dict[str, Any] = {}
_lock = asyncio.Lock()

# --- Indekslar ---
_by_id: dict[int, dict] = {}
_by_user: dict[int, list[dict]] = {}
_by_slot: dict[tuple[str, str, str], int] = {}


def _empty_db() -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "settings": {},
        "users": {},
        "admins": {},
        "appointments": [],
        "next_id": 1,
        "next_dept_id": 1,
        # Har saqlashda oshib boradi. Zaxira bilan solishtirganda
        # "qaysi nusxa yangiroq" degan savolga ANIQ javob beradi.
        "revision": 0,
        "saved_at": "",
    }


def _default_settings() -> dict[str, Any]:
    """Panel orqali o'zgartiriladigan sozlamalarning boshlang'ich holati."""
    return {
        "departments": {
            key: {"name": info["name"], "times": list(info["times"]), "order": i}
            for i, (key, info) in enumerate(DEFAULT_DEPARTMENTS.items())
        },
        "rules": {
            "booking_days_ahead": DEFAULT_RULES["booking_days_ahead"],
            "max_active_bookings": DEFAULT_RULES["max_active_bookings"],
            "min_lead_minutes": DEFAULT_RULES["min_lead_minutes"],
            "weekend_days": list(DEFAULT_RULES["weekend_days"]),
        },
        "clinic": dict(DEFAULT_CLINIC),
        "reminders": dict(DEFAULT_REMINDERS),
    }


# --------------------------------------------------------------------------
# Fayl bilan ishlash
# --------------------------------------------------------------------------

def _read_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.error("data.json o'qib bo'lmadi (%s): %s", path.name, e)
        return None


def _write_atomic(path: Path, payload: str) -> None:
    """Faylni atomar yozadi: yozish jarayoni uzilsa ham eski nusxa buzilmaydi."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())  # ma'lumot diskka fizik yozilishini kafolatlaydi
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    os.replace(tmp, path)  # atomar almashtirish


async def _persist() -> None:
    """Xotiradagi holatni diskka yozadi (fayl amali alohida oqimda — event loop bloklanmaydi)."""
    _data["revision"] = int(_data.get("revision", 0)) + 1
    _data["saved_at"] = now().isoformat(timespec="seconds")
    payload = json.dumps(_data, ensure_ascii=False, indent=2)
    await asyncio.to_thread(_write_atomic, DATA_PATH, payload)


def revision() -> int:
    """Bazaning joriy versiyasi — zaxira bilan solishtirish uchun."""
    return int(_data.get("revision", 0))


def saved_at() -> str:
    return _data.get("saved_at", "")


def _reindex() -> None:
    """Uchala indeksni noldan quradi."""
    _by_id.clear()
    _by_user.clear()
    _by_slot.clear()
    for appt in _data["appointments"]:
        _by_id[appt["id"]] = appt
        _by_user.setdefault(appt["user_id"], []).append(appt)
        if appt["status"] == ACTIVE:
            _by_slot[(appt["service_key"], appt["booking_date"], appt["booking_time"])] = appt["id"]


# --------------------------------------------------------------------------
# Ulanish
# --------------------------------------------------------------------------

async def connect() -> None:
    """Bazani yuklaydi (yoki yangisini yaratadi), indekslaydi va parolni o'rnatadi."""
    global _data

    loaded = await asyncio.to_thread(_read_file, DATA_PATH)

    if loaded is None and DATA_PATH.with_suffix(DATA_PATH.suffix + ".bak").exists():
        log.warning("Asosiy fayl buzilgan — zaxira nusxadan (.bak) tiklanmoqda")
        loaded = await asyncio.to_thread(_read_file, DATA_PATH.with_suffix(DATA_PATH.suffix + ".bak"))

    _data = loaded or _empty_db()

    # Yetishmayotgan kalitlarni to'ldirish (eski/qo'lda tahrirlangan fayl uchun)
    for key, default in _empty_db().items():
        _data.setdefault(key, default)
    _data["version"] = SCHEMA_VERSION

    _reindex()
    await _seed_settings()
    await _seed_password()

    log.info(
        "Baza yuklandi: %s (bemorlar: %d, navbatlar: %d, adminlar: %d)",
        DATA_PATH.name, len(_data["users"]), len(_data["appointments"]), len(_data["admins"]),
    )


async def close() -> None:
    async with _lock:
        await _persist()
    log.info("Baza diskka saqlandi")


# --------------------------------------------------------------------------
# Sozlamalar
# --------------------------------------------------------------------------

async def get_setting(key: str) -> str | None:
    return _data["settings"].get(key)


async def set_setting(key: str, value) -> None:
    async with _lock:
        _data["settings"][key] = value
        await _persist()


async def _seed_settings() -> None:
    """Yetishmayotgan sozlamalarni boshlang'ich qiymatlar bilan to'ldiradi.

    Faqat YO'Q bo'lganlari qo'shiladi — super admin panelda o'zgartirgan
    qiymatlar hech qachon ustiga yozilmaydi.
    """
    settings = _data["settings"]
    changed = False

    for section, defaults in _default_settings().items():
        if section not in settings:
            settings[section] = defaults
            changed = True
        elif isinstance(defaults, dict) and section != "departments":
            for field, value in defaults.items():
                if field not in settings[section]:
                    settings[section][field] = value
                    changed = True

    if "next_dept_id" not in _data:
        _data["next_dept_id"] = 1
        changed = True

    if changed:
        async with _lock:
            await _persist()
        log.info("Sozlamalar boshlang'ich qiymatlar bilan to'ldirildi")


# --------------------------------------------------------------------------
# Sozlamalarni O'QISH — sinxron, chunki hammasi xotirada turadi
# --------------------------------------------------------------------------

def departments() -> dict[str, dict]:
    """Bo'limlar, admin belgilagan tartibda."""
    items = _data["settings"].get("departments", {})
    return dict(sorted(items.items(), key=lambda kv: (kv[1].get("order", 0), kv[0])))


def department(key: str) -> dict | None:
    return _data["settings"].get("departments", {}).get(key)


def dept_name(key: str) -> str:
    """Bo'lim kalitidan nomini qaytaradi.

    O'chirilgan bo'lim uchun ham xavfsiz — eski navbatlar buzilmaydi.
    """
    info = department(key)
    if info:
        return info["name"]
    first = next(iter(departments().values()), None)
    return first["name"] if first else "🦷 Qabul"


def dept_times(key: str) -> list[str]:
    info = department(key)
    return list(info["times"]) if info else []


def rules() -> dict:
    return _data["settings"].get("rules", {})


def rule(name: str):
    return rules().get(name, DEFAULT_RULES.get(name))


def clinic() -> dict:
    return _data["settings"].get("clinic", dict(DEFAULT_CLINIC))


def reminders() -> dict:
    return _data["settings"].get("reminders", dict(DEFAULT_REMINDERS))


# --------------------------------------------------------------------------
# Sozlamalarni O'ZGARTIRISH (admin paneli uchun)
# --------------------------------------------------------------------------

async def set_rule(name: str, value) -> None:
    async with _lock:
        _data["settings"].setdefault("rules", {})[name] = value
        await _persist()
    log.info("Sozlama o'zgartirildi: rules.%s = %r", name, value)


async def set_reminder(field: str, value) -> None:
    async with _lock:
        _data["settings"].setdefault("reminders", {})[field] = value
        await _persist()
    log.info("Sozlama o'zgartirildi: reminders.%s = %r", field, value)


async def set_clinic(field: str, value: str) -> None:
    async with _lock:
        _data["settings"].setdefault("clinic", {})[field] = value
        await _persist()
    log.info("Sozlama o'zgartirildi: clinic.%s", field)


async def add_department(name: str, times: list[str]) -> str:
    """Yangi bo'lim qo'shadi va uning kalitini qaytaradi.

    Kalit qisqa ('d3') — callback_data 64 bayt limitiga sig'ishi uchun.
    """
    async with _lock:
        depts = _data["settings"].setdefault("departments", {})

        key = f"d{_data['next_dept_id']}"
        while key in depts:  # nazariy to'qnashuv
            _data["next_dept_id"] += 1
            key = f"d{_data['next_dept_id']}"
        _data["next_dept_id"] += 1

        order = max((d.get("order", 0) for d in depts.values()), default=-1) + 1
        depts[key] = {"name": name, "times": list(times), "order": order}
        await _persist()

    log.info("Yangi bo'lim qo'shildi: %s (%s)", key, name)
    return key


async def update_department(key: str, name: str | None = None, times: list[str] | None = None) -> bool:
    async with _lock:
        info = _data["settings"].get("departments", {}).get(key)
        if not info:
            return False
        if name is not None:
            info["name"] = name
        if times is not None:
            info["times"] = list(times)
        await _persist()

    log.info("Bo'lim yangilandi: %s", key)
    return True


async def update_department_order(key: str, order: int) -> bool:
    async with _lock:
        info = _data["settings"].get("departments", {}).get(key)
        if not info:
            return False
        info["order"] = order
        await _persist()
        return True


async def reset_settings() -> None:
    """Sozlamalarni standart holatga qaytaradi.

    Bemorlar, navbatlar, adminlar va PAROL tegilmaydi — faqat bo'limlar,
    ish soatlari, navbat qoidalari va klinika ma'lumotlari tiklanadi.
    """
    async with _lock:
        password = _data["settings"].get("admin_password")
        _data["settings"] = _default_settings()
        if password:
            _data["settings"]["admin_password"] = password
        await _persist()
    log.warning("Sozlamalar standart holatga qaytarildi")


async def delete_department(key: str) -> bool:
    async with _lock:
        depts = _data["settings"].get("departments", {})
        if key not in depts or len(depts) <= 1:  # oxirgi bo'limni o'chirib bo'lmaydi
            return False
        del depts[key]
        await _persist()

    log.info("Bo'lim o'chirildi: %s", key)
    return True


def active_bookings_in_department(key: str) -> int:
    """O'chirishdan oldin ogohlantirish uchun: bu bo'limda nechta faol navbat bor."""
    today = now().strftime("%Y-%m-%d")
    return sum(
        1 for (dept, date, _time) in _by_slot
        if dept == key and date >= today
    )


# --------------------------------------------------------------------------
# Parol (PBKDF2-SHA256 — ochiq matnda saqlanmaydi)
# --------------------------------------------------------------------------

def _hash(raw: str, salt: bytes, rounds: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", raw.encode(), salt, rounds).hex()


def hash_password(raw: str) -> str:
    salt = secrets.token_bytes(16)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${_hash(raw, salt, PBKDF2_ROUNDS)}"


def check_password(raw: str, stored: str) -> bool:
    try:
        algo, rounds, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = _hash(raw, bytes.fromhex(salt_hex), int(rounds))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, digest_hex)


async def _seed_password() -> None:
    if _data["settings"].get("admin_password") is None:
        # hash hisoblash ~0.1 s — event loop'ni bloklamaslik uchun alohida oqimda
        _data["settings"]["admin_password"] = await asyncio.to_thread(hash_password, DEFAULT_ADMIN_PASSWORD)
        async with _lock:
            await _persist()
        log.warning("Boshlang'ich admin paroli o'rnatildi — panelga kirgach uni almashtiring!")


async def verify_admin_password(raw: str) -> bool:
    stored = _data["settings"].get("admin_password")
    if not stored:
        return False
    return await asyncio.to_thread(check_password, raw, stored)


async def change_admin_password(raw: str) -> None:
    new_hash = await asyncio.to_thread(hash_password, raw)
    await set_setting("admin_password", new_hash)


# --------------------------------------------------------------------------
# Foydalanuvchilar
# --------------------------------------------------------------------------

async def save_user(user_id: int, full_name: str, username: str | None, phone: str) -> None:
    async with _lock:
        key = str(user_id)
        existing = _data["users"].get(key, {})
        _data["users"][key] = {
            "user_id": user_id,
            "full_name": full_name,
            "username": username,
            "phone": phone,
            "created_at": existing.get("created_at") or now().isoformat(timespec="seconds"),
        }
        await _persist()


async def get_user(user_id: int) -> dict | None:
    return _data["users"].get(str(user_id))


async def is_registered(user_id: int) -> bool:
    user = _data["users"].get(str(user_id))
    return bool(user and user.get("phone"))


async def count_users() -> int:
    return len(_data["users"])


# --------------------------------------------------------------------------
# Adminlar
# --------------------------------------------------------------------------

async def is_admin(user_id: int) -> bool:
    return str(user_id) in _data["admins"]


async def is_super_admin(user_id: int) -> bool:
    admin = _data["admins"].get(str(user_id))
    return bool(admin and admin.get("is_super"))


async def count_admins() -> int:
    return len(_data["admins"])


async def list_admins() -> list[dict]:
    """Super adminlar birinchi, keyin qo'shilgan vaqti bo'yicha."""
    return sorted(
        _data["admins"].values(),
        key=lambda a: (not a.get("is_super"), a.get("added_at") or "", a["user_id"]),
    )


async def get_admin(user_id: int) -> dict | None:
    return _data["admins"].get(str(user_id))


async def admin_ids() -> list[int]:
    return [a["user_id"] for a in _data["admins"].values()]


async def add_admin(
    user_id: int,
    full_name: str | None,
    username: str | None,
    added_by: int | None = None,
    force_super: bool = False,
) -> bool:
    """Adminni qo'shadi/yangilaydi.

    BIRINCHI qo'shilgan admin avtomatik SUPER ADMIN bo'ladi.
    Qaytaradi: True — bu foydalanuvchi super admin.
    """
    async with _lock:
        key = str(user_id)
        existing = _data["admins"].get(key)
        is_super = bool(
            force_super
            or (existing and existing.get("is_super"))  # mavjud super status yo'qolmaydi
            or not _data["admins"]  # birinchi admin
        )
        _data["admins"][key] = {
            "user_id": user_id,
            "full_name": full_name,
            "username": username,
            "is_super": is_super,
            "added_by": existing.get("added_by") if existing else added_by,
            "added_at": (existing.get("added_at") if existing else None) or now().isoformat(timespec="seconds"),
        }
        await _persist()
        return is_super


async def remove_admin(user_id: int) -> bool:
    """Adminni chiqaradi. Super adminni o'chirib bo'lmaydi."""
    async with _lock:
        key = str(user_id)
        admin = _data["admins"].get(key)
        if not admin or admin.get("is_super"):
            return False
        del _data["admins"][key]
        await _persist()
        return True


# --------------------------------------------------------------------------
# Navbatlar
# --------------------------------------------------------------------------

def _with_user(appt: dict) -> dict:
    """Navbatga bemor ma'lumotini qo'shib beradi (SQL'dagi JOIN o'rnida)."""
    user = _data["users"].get(str(appt["user_id"])) or {}
    return {
        **appt,
        "full_name": user.get("full_name"),
        "phone": user.get("phone"),
        "username": user.get("username"),
    }


async def booked_times(service_key: str, date_str: str) -> set[str]:
    """Berilgan BO'LIM va kundagi band soatlar.

    Indeks tufayli boshqa bo'limlar bir-biriga xalaqit bermaydi.
    """
    times = {t for (key, date, t) in _by_slot if key == service_key and date == date_str}
    return times


async def user_booking_on_date(user_id: int, date_str: str) -> dict | None:
    for appt in _by_user.get(user_id, ()):
        if appt["booking_date"] == date_str and appt["status"] == ACTIVE:
            return appt
    return None


async def active_bookings_of(user_id: int) -> list[dict]:
    today = now().strftime("%Y-%m-%d")
    rows = [
        a for a in _by_user.get(user_id, ())
        if a["status"] == ACTIVE and a["booking_date"] >= today
    ]
    return sorted(rows, key=lambda a: (a["booking_date"], a["booking_time"]))


async def count_active_bookings(user_id: int) -> int:
    return len(await active_bookings_of(user_id))


async def create_booking(
    user_id: int, service_key: str, service_name: str, date_str: str, time_str: str
) -> int | None:
    """Navbat yozadi. Soat band bo'lsa None qaytaradi.

    Tekshirish va yozish bitta lock ichida — shu sababli ikki bemor
    bir vaqtda bosgan taqdirda ham ikkalasiga bitta soat berilmaydi.
    """
    slot = (service_key, date_str, time_str)
    async with _lock:
        if slot in _by_slot:
            return None

        appt = {
            "id": _data["next_id"],
            "user_id": user_id,
            "service_key": service_key,
            "service_name": service_name,
            "booking_date": date_str,
            "booking_time": time_str,
            "status": ACTIVE,
            "created_at": now().isoformat(timespec="seconds"),
            "cancelled_at": None,
        }
        _data["next_id"] += 1
        _data["appointments"].append(appt)

        _by_id[appt["id"]] = appt
        _by_user.setdefault(user_id, []).append(appt)
        _by_slot[slot] = appt["id"]

        await _persist()
        return appt["id"]


async def get_booking(app_id: int) -> dict | None:
    appt = _by_id.get(app_id)
    return _with_user(appt) if appt else None


async def cancel_booking(app_id: int, user_id: int | None = None) -> bool:
    """Navbatni bekor qiladi (o'chirmaydi — tarix saqlanadi).

    user_id berilsa, FAQAT o'sha foydalanuvchining navbati bekor qilinadi.
    Shu tekshiruv boshqa bemorning navbatini o'chirib yuborishning oldini oladi.
    """
    async with _lock:
        appt = _by_id.get(app_id)
        if not appt or appt["status"] != ACTIVE:
            return False
        if user_id is not None and appt["user_id"] != user_id:
            return False

        appt["status"] = CANCELLED
        appt["cancelled_at"] = now().isoformat(timespec="seconds")
        # Soat bo'shaydi — boshqa bemor band qila oladi
        _by_slot.pop((appt["service_key"], appt["booking_date"], appt["booking_time"]), None)

        await _persist()
        return True


async def mark_booking(app_id: int, status: str) -> bool:
    """Navbat holatini o'zgartiradi: 'done' (keldi) yoki 'missed' (kelmadi)."""
    if status not in (DONE, MISSED):
        return False
    async with _lock:
        appt = _by_id.get(app_id)
        if not appt or appt["status"] != ACTIVE:
            return False
        appt["status"] = status
        _by_slot.pop((appt["service_key"], appt["booking_date"], appt["booking_time"]), None)
        await _persist()
        return True


def _upcoming() -> list[dict]:
    today = now().strftime("%Y-%m-%d")
    rows = [
        _by_id[app_id] for app_id in _by_slot.values()
        if _by_id[app_id]["booking_date"] >= today
    ]
    return sorted(rows, key=lambda a: (a["booking_date"], a["booking_time"]))


def active_future_bookings() -> list[dict]:
    """Bugundan boshlab barcha faol navbatlar (eslatmalar uchun)."""
    return [_by_id[app_id] for app_id in _by_slot.values()
            if _by_id[app_id]["booking_date"] >= now().strftime("%Y-%m-%d")]


async def mark_reminded(app_id: int, kind: str) -> bool:
    """Eslatma yuborilganini belgilaydi — takror yuborilmasligi uchun."""
    async with _lock:
        appt = _by_id.get(app_id)
        if not appt:
            return False
        appt.setdefault("reminded", {})[kind] = True
        await _persist()
        return True


async def upcoming_bookings(limit: int, offset: int) -> list[dict]:
    return [_with_user(a) for a in _upcoming()[offset:offset + limit]]


async def count_upcoming_bookings() -> int:
    return len(_upcoming())


async def stats() -> dict[str, int]:
    today = now().strftime("%Y-%m-%d")
    week_start = (now() - timedelta(days=7)).strftime("%Y-%m-%d")

    today_count = done_week = cancelled_week = 0
    for appt in _data["appointments"]:
        if appt["status"] == ACTIVE and appt["booking_date"] == today:
            today_count += 1
        if appt["booking_date"] >= week_start:
            if appt["status"] == DONE:
                done_week += 1
            elif appt["status"] == CANCELLED:
                cancelled_week += 1

    return {
        "users": len(_data["users"]),
        "admins": len(_data["admins"]),
        "today": today_count,
        "upcoming": await count_upcoming_bookings(),
        "done_week": done_week,
        "cancelled_week": cancelled_week,
        "total": len(_data["appointments"]),
    }


# --------------------------------------------------------------------------
# Xizmat amallari
# --------------------------------------------------------------------------

async def purge_old(before_date: str) -> int:
    """Berilgan sanadan oldingi yopilgan navbatlarni tozalaydi (fayl cheksiz o'smasligi uchun)."""
    async with _lock:
        before = len(_data["appointments"])
        _data["appointments"] = [
            a for a in _data["appointments"]
            if a["status"] == ACTIVE or a["booking_date"] >= before_date
        ]
        removed = before - len(_data["appointments"])
        if removed:
            _reindex()
            await _persist()
        return removed


def snapshot() -> dict[str, Any]:
    """Diagnostika/eksport uchun bazaning nusxasi."""
    return json.loads(json.dumps(_data, ensure_ascii=False))
