"""Eski SQLite bazasini (dental_bot.db) yangi JSON formatiga o'tkazadi.

Ishlatish:
    python migrate_to_json.py                 # dental_bot.db -> data.json
    python migrate_to_json.py eski.db yangi.json

Skript eski faylga TEGMAYDI — faqat o'qiydi.
Ikkala sxemani ham tushunadi:
  * eng eski:  (id, user_id, booking_date, booking_time, status)
  * o'rtadagi: + service_type
  * yangi:     + service_key, service_name, created_at, cancelled_at
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from config import DATA_PATH, LEGACY_DB_PATH, TIMEZONE

SCHEMA_VERSION = 2
DEFAULT_SERVICE = "🦷 Davolash bo'limi"


def _columns(cur: sqlite3.Cursor, table: str) -> set[str]:
    cur.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def _tables(cur: sqlite3.Cursor) -> set[str]:
    cur.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row[0] for row in cur.fetchall()}


def _service_key(name: str | None) -> str:
    """Bo'lim NOMIdan uning kalitini aniqlaydi (eski bazada faqat nom saqlangan)."""
    return "consultation" if name and "Maslahat" in name else "treatment"


def convert(db_path: Path, json_path: Path) -> dict:
    if not db_path.exists():
        raise SystemExit(f"❌ SQLite fayli topilmadi: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    tables = _tables(cur)

    data = {
        "version": SCHEMA_VERSION,
        "settings": {},
        "users": {},
        "admins": {},
        "appointments": [],
        "next_id": 1,
    }

    # --- users ---
    if "users" in tables:
        cols = _columns(cur, "users")
        for row in cur.execute("SELECT * FROM users"):
            uid = row["user_id"]
            data["users"][str(uid)] = {
                "user_id": uid,
                "full_name": row["full_name"] if "full_name" in cols else None,
                "username": row["username"] if "username" in cols else None,
                "phone": row["phone"] if "phone" in cols else None,
                "created_at": (row["created_at"] if "created_at" in cols else "") or "",
            }
        print(f"  ✅ bemorlar: {len(data['users'])} ta")

    # --- admins (faqat yangi sxemada bo'lishi mumkin) ---
    if "admins" in tables:
        for row in cur.execute("SELECT * FROM admins"):
            data["admins"][str(row["user_id"])] = {
                "user_id": row["user_id"],
                "full_name": row["full_name"],
                "username": row["username"],
                "is_super": bool(row["is_super"]),
                "added_by": row["added_by"],
                "added_at": row["added_at"] or "",
            }
        print(f"  ✅ adminlar: {len(data['admins'])} ta")

    # --- settings ---
    if "settings" in tables:
        for row in cur.execute("SELECT key, value FROM settings"):
            data["settings"][row["key"]] = row["value"]
        print(f"  ✅ sozlamalar: {len(data['settings'])} ta")

    # --- appointments ---
    if "queue_appointments" in tables:
        cols = _columns(cur, "queue_appointments")
        max_id = 0
        seen_slots: set[tuple[str, str, str]] = set()

        for row in cur.execute("SELECT * FROM queue_appointments ORDER BY id"):
            # Bo'lim nomi/kaliti — eski sxemalarda ular bo'lmasligi mumkin
            if "service_name" in cols and row["service_name"]:
                name = row["service_name"]
            elif "service_type" in cols and row["service_type"]:
                name = row["service_type"]
            else:
                name = DEFAULT_SERVICE

            key = row["service_key"] if "service_key" in cols and row["service_key"] else _service_key(name)
            status = (row["status"] if "status" in cols else None) or "active"
            slot = (key, row["booking_date"], row["booking_time"])

            # Eski bazadagi UNIQUE cheklovi bo'limni hisobga olmagani uchun
            # nazariy jihatdan takror faol slot uchrashi mumkin — birinchisini qoldiramiz.
            if status == "active":
                if slot in seen_slots:
                    print(f"  ⚠️  takror band slot topildi, 'cancelled' qilindi: #{row['id']} {slot}")
                    status = "cancelled"
                else:
                    seen_slots.add(slot)

            data["appointments"].append({
                "id": row["id"],
                "user_id": row["user_id"],
                "service_key": key,
                "service_name": name,
                "booking_date": row["booking_date"],
                "booking_time": row["booking_time"],
                "status": status,
                "created_at": (row["created_at"] if "created_at" in cols else "") or "",
                "cancelled_at": row["cancelled_at"] if "cancelled_at" in cols else None,
            })
            max_id = max(max_id, row["id"])

        data["next_id"] = max_id + 1
        print(f"  ✅ navbatlar: {len(data['appointments'])} ta (keyingi id: {data['next_id']})")

    conn.close()

    # Mavjud data.json ustiga yozishdan oldin zaxira nusxa
    if json_path.exists():
        backup = json_path.with_name(
            f"{json_path.stem}.{datetime.now(TIMEZONE).strftime('%Y%m%d-%H%M%S')}.bak.json"
        )
        backup.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 eski JSON zaxiralandi: {backup.name}")

    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else LEGACY_DB_PATH
    json_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DATA_PATH

    print("🔄 SQLite -> JSON o'tkazish")
    print(f"   manba:  {db_path}")
    print(f"   natija: {json_path}\n")

    convert(db_path, json_path)

    print(f"\n✅ Tayyor! {json_path.name} yaratildi "
          f"({json_path.stat().st_size:,} bayt)".replace(",", " "))
    print("\n⚠️  Eski .db fayli o'chirilmadi. Botni tekshirib ko'ring, keyin qo'lda o'chiring.")
    print("⚠️  data.json bemorlarning shaxsiy ma'lumotlarini saqlaydi — git'ga qo'shilmasin!")


if __name__ == "__main__":
    main()
