"""Botning biznes-mantiqini tekshiruvchi testlar (Telegram'ga ulanmaydi).

Ishga tushirish:
    python tests.py

Hech qanday qo'shimcha kutubxona kerak emas — oddiy assert'lar.
Testlar vaqtinchalik papkada ishlaydi, haqiqiy data.json ga tegmaydi.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

# Testlar uchun vaqtinchalik muhit — config import qilinishidan OLDIN o'rnatiladi
_TMP = Path(tempfile.mkdtemp(prefix="navbat_test_"))
os.environ["BOT_TOKEN"] = "111111:TEST-TOKEN"
os.environ["DATA_FILE"] = str(_TMP / "data.json")
os.environ.setdefault("TIMEZONE", "Asia/Tashkent")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config  # noqa: E402
import storage as db  # noqa: E402
import keyboards as kb  # noqa: E402
from callbacks import AdminQueueCB, SlotCB, UserBookingCB  # noqa: E402
from handlers.common import normalize_phone  # noqa: E402
from utils import esc, is_slot_bookable, now, pretty_date, slot_datetime  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []

TREAT = "🦷 Davolash bo'limi"
CONSULT = "👨‍⚕️ Maslahat olish"
FUTURE = "2099-06-10"


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  ✅ {name}")
    else:
        FAILED.append(f"{name} — {detail}" if detail else name)
        print(f"  ❌ {name}  {detail}")


async def fresh_db() -> None:
    """Har bir blok uchun toza baza."""
    for suffix in ("", ".bak", ".tmp"):
        p = Path(str(config.DATA_PATH) + suffix)
        p.unlink(missing_ok=True)
    await db.connect()


# --------------------------------------------------------------------------

async def test_utils() -> None:
    print("\n📦 Yordamchi funksiyalar")

    check("vaqt zonasi Asia/Tashkent (+5)", now().utcoffset().total_seconds() == 5 * 3600,
          f"olindi: {now().utcoffset()}")
    check("o'tgan vaqt bron qilinmaydi", not is_slot_bookable("2020-01-01", "09:00"))
    check("kelajakdagi vaqt bron qilinadi", is_slot_bookable(FUTURE, "09:00"))
    check("slot_datetime tz bilan", slot_datetime(FUTURE, "09:00").tzinfo is not None)
    check("pretty_date", pretty_date("2026-09-16") == "16.09.2026 (Chorshanba)",
          pretty_date("2026-09-16"))
    check("buzuq sana yiqilmaydi", pretty_date("salom") == "salom")

    # HTML escaping — eski kodda Markdown ishlatilgani uchun bunday ism botni yiqitardi
    check("HTML escaping", esc("<b>Ali</b> & Vali") == "&lt;b&gt;Ali&lt;/b&gt; &amp; Vali",
          esc("<b>Ali</b> & Vali"))
    check("None -> tire", esc(None) == "—")

    cases = {
        "+998901234567": "+998901234567",
        "998901234567": "+998901234567",
        "901234567": "+998901234567",
        "+998 90 123 45 67": "+998901234567",
        "90-123-45-67": "+998901234567",
        "(90) 123-45-67": "+998901234567",
        "12345": None,
        "salom": None,
        "": None,
    }
    for raw, expected in cases.items():
        check(f"telefon {raw!r:20} -> {expected}", normalize_phone(raw) == expected,
              f"olindi: {normalize_phone(raw)}")


async def test_admin_ids_parsing() -> None:
    print("\n📦 ADMIN_ID ro'yxati (.env)")
    from config import _parse_ids

    cases = {
        "": [],
        "[]": [],
        "   ": [],
        "637554472": [637554472],
        "[637554472]": [637554472],
        "[637554472, 123456789]": [637554472, 123456789],
        "637554472,123456789": [637554472, 123456789],
        "637554472 123456789": [637554472, 123456789],
        "[ 637554472 , 123456789 ]": [637554472, 123456789],
        "637554472, 637554472": [637554472],  # takror olib tashlanadi
        "'637554472'": [637554472],
    }
    for raw, expected in cases.items():
        check(f"ADMIN_ID={raw!r:26} -> {expected}", _parse_ids(raw) == expected,
              f"olindi: {_parse_ids(raw)}")

    try:
        _parse_ids("salom")
        check("harfli qiymat rad etiladi", False, "xato chiqmadi")
    except RuntimeError as e:
        check("harfli qiymat tushunarli xato beradi", "butun sonlardan" in str(e))


async def test_backup_config() -> None:
    print("\n📦 GitHub zaxirasi")
    from backup import GitHubBackup

    off = GitHubBackup(repo="", token="", local_path=config.DATA_PATH)
    check("sozlanmagan zaxira o'chiq", not off.enabled)
    check("o'chiq zaxira yuklamaydi", not await off.upload())
    check("o'chiq zaxira tiklamaydi", not await off.restore_if_empty())
    check("o'chiq holat matni", "o'chiq" in off.status_line(), off.status_line())
    check("verify() o'chiqda False", not await off.verify())

    on = GitHubBackup(repo="user/private-repo", token="ghp_test", local_path=config.DATA_PATH)
    check("sozlangan zaxira yoqilgan", on.enabled)
    check("yoqilgan holat matni", "yoqilgan" in on.status_line(), on.status_line())
    check("interval soniyaga aylandi", on.interval == config.BACKUP_INTERVAL_MINUTES * 60)
    check("0 interval 1 daqiqaga ko'tariladi",
          GitHubBackup(repo="a/b", token="t", interval_minutes=0).interval == 60)

    # _local_has_data — tiklash kerakmi yoki yo'qligini aniqlaydi
    await fresh_db()
    tmp = config.DATA_PATH
    b = GitHubBackup(repo="a/b", token="t", local_path=tmp)
    await db.close()
    check("bo'sh baza 'ma'lumot yo'q' deb hisoblanadi", not b._local_has_data())

    await db.connect()
    await db.save_user(555, "Ali", None, "+998901112233")
    await db.close()
    check("bemor qo'shilgach 'ma'lumot bor'", b._local_has_data())

    missing = GitHubBackup(repo="a/b", token="t", local_path=Path(str(tmp) + ".yoq"))
    check("fayl yo'q bo'lsa 'ma'lumot yo'q'", not missing._local_has_data())

    check("hash o'zgarishni aniqlaydi",
          GitHubBackup._digest(b"a") != GitHubBackup._digest(b"b"))


async def test_callbacks() -> None:
    print("\n📦 Callback data (64 bayt limiti va ':' muammosi)")

    cb = SlotCB(key="consultation", date="2026-09-16", time="09:30")
    packed = cb.pack()
    check("soatdagi ':' callback'ni buzmaydi", SlotCB.unpack(packed).time == "09:30", packed)
    check("bo'lim to'g'ri qaytdi", SlotCB.unpack(packed).key == "consultation")
    check(f"64 bayt limitiga sig'adi ({len(packed.encode())} bayt)", len(packed.encode()) <= 64)

    q = AdminQueueCB(action="notify", id=999999, page=12)
    check("admin callback round-trip", AdminQueueCB.unpack(q.pack()).id == 999999)
    check("UserBookingCB round-trip", UserBookingCB.unpack(UserBookingCB(action="yes", id=7).pack()).action == "yes")


async def test_password() -> None:
    print("\n📦 Parol")
    await fresh_db()

    check("boshlang'ich parol ishlaydi", await db.verify_admin_password("1234567890"))
    check("xato parol rad etiladi", not await db.verify_admin_password("qwerty"))
    check("parol ochiq saqlanmaydi", "1234567890" not in json.dumps(db.snapshot()))
    check("hash PBKDF2 formatida",
          db.snapshot()["settings"]["admin_password"].startswith("pbkdf2_sha256$200000$"))

    await db.change_admin_password("Yangi-Parol-2026")
    check("eski parol endi ishlamaydi", not await db.verify_admin_password("1234567890"))
    check("yangi parol ishlaydi", await db.verify_admin_password("Yangi-Parol-2026"))
    check("buzuq hash yiqilmaydi", db.check_password("x", "chala-hash") is False)


async def test_admins() -> None:
    print("\n📦 Adminlar")
    await fresh_db()

    check("boshida admin yo'q", await db.count_admins() == 0)
    check("1-kirgan odam SUPER admin", await db.add_admin(100, "Birinchi", "first") is True)
    check("2-kirgan odam oddiy admin", await db.add_admin(200, "Ikkinchi", "second", added_by=100) is False)
    check("3-kirgan odam oddiy admin", await db.add_admin(300, "Uchinchi", None, added_by=100) is False)

    check("is_super(100)", await db.is_super_admin(100))
    check("is_super(200) emas", not await db.is_super_admin(200))
    check("is_admin(200)", await db.is_admin(200))
    check("is_admin(999) emas", not await db.is_admin(999))
    check("adminlar soni 3", await db.count_admins() == 3)

    listed = await db.list_admins()
    check("ro'yxatda super birinchi", listed[0]["user_id"] == 100)
    check("ro'yxat to'liq", [a["user_id"] for a in listed] == [100, 200, 300],
          str([a["user_id"] for a in listed]))

    check("SUPER adminni o'chirib BO'LMAYDI", not await db.remove_admin(100))
    check("super hali ham ro'yxatda", await db.is_admin(100))
    check("oddiy admin chiqarildi", await db.remove_admin(200))
    check("chiqarilgan admin yo'q", not await db.is_admin(200))
    check("mavjud bo'lmaganni o'chirish False", not await db.remove_admin(555))
    check("adminlar soni 2 ga tushdi", await db.count_admins() == 2)

    # Qayta kirgan super admin darajasini yo'qotmasligi kerak
    await db.add_admin(100, "Birinchi (yangilangan)", "first")
    check("qayta kirgach super saqlandi", await db.is_super_admin(100))
    check("ismi yangilandi", (await db.get_admin(100))["full_name"] == "Birinchi (yangilangan)")

    # force_super — .env dagi ADMIN_ID uchun
    await fresh_db()
    await db.add_admin(1, "A", None)
    check("force_super ikkinchi super yaratadi", await db.add_admin(2, "B", None, force_super=True))
    check("ikkalasi ham super", await db.is_super_admin(1) and await db.is_super_admin(2))
    check("admin_ids to'liq", sorted(await db.admin_ids()) == [1, 2])


async def test_users_and_booking() -> None:
    print("\n📦 Bemorlar va navbatlar")
    await fresh_db()

    check("ro'yxatdan o'tmagan", not await db.is_registered(555))
    await db.save_user(555, "Ali Valiyev", "ali", "+998901112233")
    check("ro'yxatdan o'tdi", await db.is_registered(555))
    check("telefon saqlandi", (await db.get_user(555))["phone"] == "+998901112233")
    check("bemorlar soni 1", await db.count_users() == 1)

    await db.save_user(666, "Vali Aliyev", None, "+998901112244")
    await db.save_user(777, "Hasan", None, "+998901112255")

    a = await db.create_booking(555, "treatment", TREAT, FUTURE, "09:00")
    check("navbat yozildi", a == 1, f"id={a}")

    b = await db.create_booking(666, "treatment", TREAT, FUTURE, "09:00")
    check("BAND soat ikkinchi marta berilmaydi", b is None, f"id={b}")

    # Eski kodda UNIQUE(date,time) bo'lim ajratmasdi — bu holat bloklanardi
    c = await db.create_booking(666, "consultation", CONSULT, FUTURE, "09:00")
    check("boshqa BO'LIM o'sha soatga yozila oladi", c is not None)

    check("treatment band soatlari", await db.booked_times("treatment", FUTURE) == {"09:00"},
          str(await db.booked_times("treatment", FUTURE)))
    check("consultation band soatlari", await db.booked_times("consultation", FUTURE) == {"09:00"})
    check("boshqa kunda band yo'q", await db.booked_times("treatment", "2099-06-11") == set())

    check("bir kunga ikkinchi navbat topildi", (await db.user_booking_on_date(555, FUTURE))["id"] == a)
    check("boshqa kunda navbat yo'q", await db.user_booking_on_date(555, "2099-06-11") is None)

    booking = await db.get_booking(a)
    check("JOIN: bemor ismi qo'shildi", booking["full_name"] == "Ali Valiyev")
    check("JOIN: telefon qo'shildi", booking["phone"] == "+998901112233")
    check("mavjud bo'lmagan navbat None", await db.get_booking(99999) is None)

    check("faol navbatlar soni", await db.count_active_bookings(555) == 1)
    check("kutilayotganlar soni", await db.count_upcoming_bookings() == 2)


async def test_ownership() -> None:
    print("\n📦 Egalik tekshiruvi (eski koddagi asosiy xavfsizlik teshigi)")
    await fresh_db()
    await db.save_user(555, "Ali", None, "+998901112233")
    await db.save_user(666, "Vali", None, "+998901112244")

    a = await db.create_booking(555, "treatment", TREAT, FUTURE, "09:00")

    check("BEGONA odam bekor qila OLMAYDI", not await db.cancel_booking(a, user_id=666))
    check("navbat hali faol", (await db.get_booking(a))["status"] == "active")
    check("EGASI bekor qila oladi", await db.cancel_booking(a, user_id=555))
    check("status 'cancelled' bo'ldi", (await db.get_booking(a))["status"] == "cancelled")
    check("cancelled_at yozildi", (await db.get_booking(a))["cancelled_at"] is not None)
    check("navbat O'CHIRILMADI (tarix saqlandi)", await db.get_booking(a) is not None)
    check("ikkinchi marta bekor qilib bo'lmaydi", not await db.cancel_booking(a, user_id=555))

    check("bekor qilingach soat BO'SHADI", await db.booked_times("treatment", FUTURE) == set())
    d = await db.create_booking(666, "treatment", TREAT, FUTURE, "09:00")
    check("bo'shagan soatga boshqa bemor yozildi", d is not None)

    # Admin user_id'siz ham bekor qila oladi
    check("admin istalgan navbatni bekor qiladi", await db.cancel_booking(d))

    e = await db.create_booking(555, "treatment", TREAT, FUTURE, "10:30")
    check("'keldi' belgilandi", await db.mark_booking(e, "done"))
    check("'done' dan keyin soat bo'shaydi", "10:30" not in await db.booked_times("treatment", FUTURE))
    check("noto'g'ri status rad etiladi", not await db.mark_booking(e, "hacked"))


async def test_race_condition() -> None:
    print("\n📦 Bir vaqtda bosish (race condition)")
    await fresh_db()

    for uid in range(1, 51):
        await db.save_user(uid, f"Bemor {uid}", None, f"+99890111{uid:04d}")

    # 50 ta bemor AYNAN bir vaqtda bitta soatni bosadi
    results = await asyncio.gather(
        *(db.create_booking(uid, "treatment", TREAT, FUTURE, "09:00") for uid in range(1, 51))
    )
    winners = [r for r in results if r is not None]
    check(f"50 ta bir vaqtdagi urinishdan FAQAT 1 tasi o'tdi (o'tdi: {len(winners)})", len(winners) == 1)
    check("bazada bitta faol navbat", await db.count_upcoming_bookings() == 1)
    check("band soat bitta", await db.booked_times("treatment", FUTURE) == {"09:00"})

    # id lar takrorlanmasligi kerak
    ids = await asyncio.gather(
        *(db.create_booking(i, "treatment", TREAT, FUTURE, t)
          for i, t in enumerate(["10:30", "12:00", "13:30", "15:00", "16:30"], start=1))
    )
    check("id lar takrorlanmadi", len(set(ids)) == len(ids), str(ids))


async def test_persistence() -> None:
    print("\n📦 Diskka saqlash va tiklash")
    await fresh_db()

    await db.save_user(555, "Ali <Test> & Co", "ali", "+998901112233")
    await db.add_admin(100, "Super", "sup")
    await db.add_admin(200, "Oddiy", None, added_by=100)
    booking_id = await db.create_booking(555, "consultation", CONSULT, FUTURE, "11:00")
    await db.change_admin_password("test-parol")
    await db.close()

    check("data.json yaratildi", config.DATA_PATH.exists())
    raw = config.DATA_PATH.read_text(encoding="utf-8")
    check("JSON to'g'ri formatda", json.loads(raw)["version"] == 2)
    check("o'zbekcha matn buzilmadi (ensure_ascii=False)", "Maslahat" in raw)
    check("JSON o'qishga qulay (indent)", "\n  " in raw)

    # Botni "qayta ishga tushirish"
    await db.connect()
    check("bemor tiklandi", (await db.get_user(555))["full_name"] == "Ali <Test> & Co")
    check("super admin tiklandi", await db.is_super_admin(100))
    check("oddiy admin tiklandi", await db.is_admin(200) and not await db.is_super_admin(200))
    check("navbat tiklandi", (await db.get_booking(booking_id))["booking_time"] == "11:00")
    check("indeks qayta qurildi", await db.booked_times("consultation", FUTURE) == {"11:00"})
    check("parol tiklandi", await db.verify_admin_password("test-parol"))

    # Yangi navbat id eskisidan katta bo'lishi kerak (id takrorlanmasin)
    new_id = await db.create_booking(555, "treatment", TREAT, FUTURE, "09:00")
    check("qayta ishga tushgach id davom etdi", new_id > booking_id, f"{booking_id} -> {new_id}")

    check("zaxira nusxa (.bak) yaratildi", Path(str(config.DATA_PATH) + ".bak").exists())
    check("vaqtinchalik .tmp fayl qolmadi", not Path(str(config.DATA_PATH) + ".tmp").exists())


async def test_corrupted_file() -> None:
    print("\n📦 Buzilgan fayldan tiklanish")
    await fresh_db()
    await db.save_user(555, "Ali", None, "+998901112233")
    await db.create_booking(555, "treatment", TREAT, FUTURE, "09:00")
    await db.close()

    # Faylni "buzamiz" (masalan, disk to'lib qolgan holat)
    config.DATA_PATH.write_text("{ bu yerda buzuq json", encoding="utf-8")
    await db.connect()
    check("buzilgan fayl .bak dan tiklandi", await db.count_users() == 1)

    # Umuman fayl yo'q bo'lsa
    for suffix in ("", ".bak"):
        Path(str(config.DATA_PATH) + suffix).unlink(missing_ok=True)
    await db.connect()
    check("fayl yo'q bo'lsa bo'sh baza yaratiladi", await db.count_users() == 0)
    check("bo'sh bazada parol o'rnatildi", await db.verify_admin_password("1234567890"))


async def test_purge() -> None:
    print("\n📦 Eski yozuvlarni tozalash")
    await fresh_db()
    await db.save_user(555, "Ali", None, "+998901112233")

    old = await db.create_booking(555, "treatment", TREAT, "2020-01-05", "09:00")
    await db.cancel_booking(old)
    keep = await db.create_booking(555, "treatment", TREAT, FUTURE, "09:00")

    removed = await db.purge_old("2021-01-01")
    check("eski yopilgan yozuv tozalandi", removed == 1, f"tozalandi: {removed}")
    check("faol navbat saqlanib qoldi", await db.get_booking(keep) is not None)
    check("indeks buzilmadi", await db.booked_times("treatment", FUTURE) == {"09:00"})


async def test_stats() -> None:
    print("\n📦 Statistika")
    await fresh_db()
    await db.save_user(555, "Ali", None, "+998901112233")
    await db.add_admin(100, "Super", None)

    today = now().strftime("%Y-%m-%d")
    await db.create_booking(555, "treatment", TREAT, today, "23:30")
    done = await db.create_booking(555, "consultation", CONSULT, today, "23:45")
    await db.mark_booking(done, "done")
    cancelled = await db.create_booking(555, "treatment", TREAT, FUTURE, "09:00")
    await db.cancel_booking(cancelled)

    s = await db.stats()
    check("bemorlar soni", s["users"] == 1, str(s))
    check("adminlar soni", s["admins"] == 1, str(s))
    check("bugungi faol navbat", s["today"] == 1, str(s))
    check("haftalik 'keldi'", s["done_week"] == 1, str(s))
    check("jami yozuvlar", s["total"] == 3, str(s))


async def test_keyboards() -> None:
    print("\n📦 Klaviaturalar")

    menu = kb.main_menu(is_admin=False)
    texts = [b.text for row in menu.keyboard for b in row]
    check("oddiy foydalanuvchida admin tugmasi YO'Q", kb.BTN_ADMIN not in texts)
    check("navbat olish tugmasi bor", kb.BTN_BOOK in texts)

    admin_texts = [b.text for row in kb.main_menu(is_admin=True).keyboard for b in row]
    check("adminda admin tugmasi bor", kb.BTN_ADMIN in admin_texts)

    super_menu = [b.text for row in kb.admin_menu(is_super=True).inline_keyboard for b in row]
    plain_menu = [b.text for row in kb.admin_menu(is_super=False).inline_keyboard for b in row]
    check("super adminda parol tugmasi bor", any("Parol" in t for t in super_menu))
    check("super adminda adminlar tugmasi bor", any("Adminlar" in t for t in super_menu))
    check("super adminda zaxira tugmasi bor", any("zaxira" in t.lower() for t in super_menu), str(super_menu))
    check("ODDIY adminda parol tugmasi YO'Q", not any("Parol" in t for t in plain_menu))
    check("ODDIY adminda adminlar tugmasi YO'Q", not any("Adminlar" in t for t in plain_menu), str(plain_menu))
    check("ODDIY adminda zaxira tugmasi YO'Q", not any("zaxira" in t.lower() for t in plain_menu), str(plain_menu))
    check("oddiy adminda navbatlar bor", any("Navbatlar" in t for t in plain_menu))
    check("oddiy adminda chiqish tugmasi bor", any("chiqish" in t.lower() for t in plain_menu))
    check("super adminda chiqish tugmasi YO'Q", not any("chiqish" in t.lower() for t in super_menu))

    days = kb.days("treatment")
    day_buttons = [b for row in days.inline_keyboard for b in row if b.callback_data.startswith("date")]
    check("kunlar ro'yxati bo'sh emas", len(day_buttons) > 0)
    check("yakshanba ko'rsatilmaydi",
          all("-" in b.callback_data for b in day_buttons))

    slots = kb.slots("treatment", FUTURE, booked={"09:00"})
    labels = [b.text for row in slots.inline_keyboard for b in row]
    check("band soat ❌ bilan belgilandi", "❌ 09:00" in labels, str(labels))
    check("bo'sh soat 🟢 bilan belgilandi", "🟢 10:30" in labels, str(labels))

    past = kb.slots("treatment", "2020-01-01", booked=set())
    check("o'tgan soatlar ⌛ bilan", all(b.text.startswith("⌛") for row in past.inline_keyboard
                                        for b in row if ":" in b.text))

    rows = [{"user_id": 1, "full_name": "Super", "is_super": True, "added_at": "", "username": None},
            {"user_id": 2, "full_name": "Oddiy", "is_super": False, "added_at": "", "username": None}]
    admins_kb = kb.admins_list(rows, viewer_is_super=True)
    del_buttons = [b.text for row in admins_kb.inline_keyboard for b in row if b.text.startswith("❌")]
    check("super adminni chiqarish tugmasi YO'Q", not any("Super" in t for t in del_buttons), str(del_buttons))
    check("oddiy adminni chiqarish tugmasi BOR", any("Oddiy" in t for t in del_buttons), str(del_buttons))

    viewer_plain = kb.admins_list(rows, viewer_is_super=False)
    check("oddiy admin hech kimni chiqara olmaydi",
          not any(b.text.startswith("❌") for row in viewer_plain.inline_keyboard for b in row))


# --------------------------------------------------------------------------

async def main() -> None:
    print("=" * 62)
    print("  Bot_navbat — testlar")
    print(f"  vaqtinchalik papka: {_TMP}")
    print("=" * 62)

    for test in (
        test_utils, test_admin_ids_parsing, test_backup_config, test_callbacks, test_password, test_admins,
        test_users_and_booking, test_ownership, test_race_condition,
        test_persistence, test_corrupted_file, test_purge, test_stats,
        test_keyboards,
    ):
        await test()

    print("\n" + "=" * 62)
    print(f"  ✅ o'tdi: {len(PASSED)}   ❌ yiqildi: {len(FAILED)}")
    if FAILED:
        print("\n  Yiqilgan testlar:")
        for name in FAILED:
            print(f"    • {name}")
    print("=" * 62)

    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    logging_off = __import__("logging")
    logging_off.disable(logging_off.WARNING)
    asyncio.run(main())
