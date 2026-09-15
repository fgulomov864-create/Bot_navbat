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

# Testlar ishlab chiquvchining .env fayliga BOG'LIQ BO'LMASLIGI kerak —
# aks holda natija kimning mashinasida ishlatilishiga qarab o'zgarib ketadi.
os.environ["SKIP_DOTENV"] = "1"

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
    check("o'chiq zaxira tiklamaydi", await off.sync_on_startup() == "disabled")
    check("o'chiq holat matni", "o'chiq" in off.status_line(), off.status_line())
    check("verify() o'chiqda False", not await off.verify())

    on = GitHubBackup(repo="user/private-repo", token="ghp_test", local_path=config.DATA_PATH)
    check("sozlangan zaxira yoqilgan", on.enabled)
    check("kalitsiz shifrlash o'chiq", not on.encrypted)
    check("kalit berilsa shifrlash yoqiladi",
          GitHubBackup(repo="a/b", token="t", encrypt_key="k").encrypted)
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


async def test_backup_encryption() -> None:
    print("\n📦 Zaxirani shifrlash")
    from backup import decrypt, encrypt, is_encrypted

    secret = json.dumps({"users": {"1": {"full_name": "Ali Valiyev", "phone": "+998901112233"}}},
                        ensure_ascii=False)

    blob = encrypt(secret, "maxfiy-kalit")
    check("shifrlangan fayl belgisi bor", is_encrypted(blob))
    check("ochiq JSON shifrlangan deb hisoblanmaydi", not is_encrypted(secret.encode()))

    # Eng muhimi: shifrlangan faylda shaxsiy ma'lumot KO'RINMASLIGI kerak
    check("ism shifrlangan faylda ko'rinmaydi", b"Ali Valiyev" not in blob)
    check("telefon shifrlangan faylda ko'rinmaydi", b"+998901112233" not in blob)
    check("'phone' kaliti ham ko'rinmaydi", b"phone" not in blob)

    check("to'g'ri kalit bilan ochiladi", decrypt(blob, "maxfiy-kalit") == secret)
    check("NOTO'G'RI kalit bilan ochilmaydi", decrypt(blob, "boshqa-kalit") is None)
    check("bo'sh kalit bilan ochilmaydi", decrypt(blob, "") is None)
    check("shifrlanmagan faylni deshifrlash None", decrypt(secret.encode(), "kalit") is None)

    buzuq = blob[:-5] + b"XXXXX"
    check("buzilgan fayl ochilmaydi (yaxlitlik tekshiriladi)", decrypt(buzuq, "maxfiy-kalit") is None)

    # Har safar yangi salt — bir xil matn har xil shifrlanadi
    check("takroriy shifrlash har xil natija beradi", encrypt(secret, "k") != encrypt(secret, "k"))
    check("lekin ikkalasi ham ochiladi",
          decrypt(encrypt(secret, "k"), "k") == decrypt(encrypt(secret, "k"), "k") == secret)


async def test_backup_restore_logic() -> None:
    print("\n📦 Zaxiradan tiklash: 'eng yangi nusxa yutadi'")
    from backup import GitHubBackup

    await fresh_db()
    path = config.DATA_PATH
    b = GitHubBackup(repo="a/b", token="t", local_path=path)

    def remote(revision: int, users: int = 1) -> str:
        return json.dumps({
            "revision": revision,
            "saved_at": "2026-09-15T10:00:00+05:00",
            "users": {str(i): {"full_name": f"Bemor {i}", "phone": "+998901112233"} for i in range(users)},
            "appointments": [],
            "admins": {},
            "settings": {},
        }, ensure_ascii=False)

    # 1) Lokal bo'sh -> zaxiradan tiklanadi
    await db.close()
    path.unlink(missing_ok=True)
    b._download = lambda: _async(remote(5, users=3))
    check("lokal yo'q -> tiklandi", await b.sync_on_startup() == "restored")
    await db.connect()
    check("tiklangan bemorlar o'qildi", await db.count_users() == 3, str(await db.count_users()))

    # 2) Lokal YANGIROQ -> tegilmaydi
    await db.save_user(999, "Yangi bemor", None, "+998901119999")
    local_rev = db.revision()
    await db.close()
    b._download = lambda: _async(remote(1))
    check("lokal yangiroq -> tiklanmadi", await b.sync_on_startup() == "local")
    await db.connect()
    check("yangi bemor o'chib ketmadi", await db.is_registered(999))
    check("revision oshib bordi", db.revision() >= local_rev)

    # 3) Zaxira YANGIROQ -> tiklanadi, lokal nusxa chetga olinadi
    await db.close()
    b._download = lambda: _async(remote(99999, users=7))
    check("zaxira yangiroq -> tiklandi", await b.sync_on_startup() == "restored")
    safety = Path(str(path) + ".before-restore.bak")
    check("lokal nusxa YO'QOLMADI (.before-restore.bak)", safety.exists())
    check("saqlangan nusxada eski bemor bor", "998901119999" in safety.read_text(encoding="utf-8"))
    await db.connect()
    check("zaxiradagi bemorlar tiklandi", await db.count_users() == 7)

    # 4) Zaxira yo'q -> lokal qoladi
    b._download = lambda: _async(None)
    check("zaxira yo'q -> lokal qoladi", await b.sync_on_startup() == "no-backup")
    await db.connect()
    check("ma'lumot joyida", await db.count_users() == 7)

    # 5) Buzilgan zaxira -> lokal qoladi (ma'lumot yo'qolmaydi)
    b._download = lambda: _async("{ buzuq json")
    check("buzilgan zaxira -> lokal qoladi", await b.sync_on_startup() == "local")
    await db.connect()
    check("buzilgan zaxira ma'lumotni buzmadi", await db.count_users() == 7)

    # 6) Zaxira o'chiq bo'lsa
    off = GitHubBackup(repo="", token="", local_path=path)
    check("o'chiq zaxira hech narsa qilmaydi", await off.sync_on_startup() == "disabled")

    safety.unlink(missing_ok=True)


def _async(value):
    """Testlarda _download() ni almashtirish uchun kichik yordamchi."""
    async def _inner():
        return value
    return _inner()


async def test_reminders() -> None:
    print("\n📦 🔔 Avtomatik eslatmalar")
    from datetime import timedelta

    import reminders as rem

    await fresh_db()
    check("standart: kun oldin yoqilgan", db.reminders()["day_before"] is True)
    check("standart: 1 soat oldin", db.reminders()["hours_before"] == 1)

    await db.save_user(555, "Ali", None, "+998901112233")

    # Yuborilgan xabarlarni yig'ib boruvchi soxta bot
    sent: list[tuple[int, str]] = []

    class FakeBot:
        async def send_message(self, chat_id, text, **kw):
            sent.append((chat_id, text))

    fake = FakeBot()

    async def make(delta: timedelta) -> int:
        moment = now() + delta
        return await db.create_booking(
            555, "treatment", TREAT, moment.strftime("%Y-%m-%d"), moment.strftime("%H:%M")
        )

    # 1) Uzoqdagi navbat — hali eslatma kerak emas
    far = await make(timedelta(days=5))
    await rem._send_due(fake)
    check("5 kun qolganda eslatma yuborilmaydi", not sent, str(sent))
    check("belgi qo'yilmadi", not (await db.get_booking(far)).get("reminded"))

    # 2) 20 soat qolgan — kunlik eslatma ketishi kerak
    sent.clear()
    day = await make(timedelta(hours=20))
    await rem._send_due(fake)
    check("20 soat qolganda kunlik eslatma ketdi", any("ertaga" in t.lower() for _, t in sent), str(sent))
    check("kunlik eslatma belgilandi", (await db.get_booking(day))["reminded"].get("day") is True)

    # 3) Takroriy yuborilmaydi
    sent.clear()
    await rem._send_due(fake)
    check("kunlik eslatma IKKI MARTA yuborilmaydi", not sent, str(sent))

    # 4) 30 daqiqa qolgan — soatlik eslatma, kunlik esa YUBORILMAYDI
    sent.clear()
    soon = await make(timedelta(minutes=30))
    await rem._send_due(fake)
    texts = " ".join(t for _, t in sent)
    check("30 daqiqa qolganda soatlik eslatma ketdi", "soatdan keyin" in texts, str(sent))
    check("bunda 'ertaga' deb yozilmadi", "ertaga" not in texts.lower(), str(sent))
    check("kunlik eslatma o'rinsiz deb belgilandi",
          (await db.get_booking(soon))["reminded"].get("day") is True)

    # 5) O'tib ketgan navbatga eslatma yo'q
    sent.clear()
    past = await db.create_booking(555, "consultation", CONSULT, "2020-01-01", "09:00")
    await rem._send_due(fake)
    check("o'tgan navbatga eslatma yuborilmaydi",
          not any(str(past) in t for _, t in sent), str(sent))

    # 6) Bekor qilingan navbatga eslatma yo'q
    sent.clear()
    cancelled = await make(timedelta(hours=10))
    await db.cancel_booking(cancelled)
    await rem._send_due(fake)
    check("bekor qilingan navbatga eslatma yo'q", not sent, str(sent))

    # 7) Sozlamalar orqali o'chirish
    await fresh_db()
    await db.save_user(555, "Ali", None, "+998901112233")
    await db.set_reminder("day_before", False)
    await db.set_reminder("hours_before", 0)
    sent.clear()
    await make(timedelta(hours=2))
    count = await rem._send_due(fake)
    check("ikkalasi o'chirilganda hech narsa yuborilmaydi", count == 0 and not sent, str(sent))

    # 8) Faqat soatlik yoqilgan
    await db.set_reminder("hours_before", 3)
    sent.clear()
    await rem._send_due(fake)
    check("faqat soatlik yoqilganda u ishlaydi", any("soatdan keyin" in t for _, t in sent), str(sent))
    check("kunlik yuborilmadi", not any("ertaga" in t.lower() for _, t in sent))


async def test_settings_storage() -> None:
    print("\n📦 Sozlamalar (bo'limlar, qoidalar, klinika)")
    await fresh_db()

    # Boshlang'ich qiymatlar config.py dan ko'chiriladi
    check("2 ta standart bo'lim", len(db.departments()) == 2, str(list(db.departments())))
    check("treatment kaliti bor", db.department("treatment") is not None)
    check("bo'lim nomi", db.dept_name("treatment") == TREAT, db.dept_name("treatment"))
    check("bo'lim soatlari", db.dept_times("treatment")[0] == "09:00")
    check("qoidalar o'rnatildi", db.rule("booking_days_ahead") == 7)
    check("dam olish kuni", db.rule("weekend_days") == [6])
    check("klinika manzili bor", bool(db.clinic().get("address")))

    # Qoidalarni o'zgartirish
    await db.set_rule("booking_days_ahead", 14)
    await db.set_rule("max_active_bookings", 5)
    await db.set_rule("weekend_days", [5, 6])
    check("oldindan kunlar o'zgardi", db.rule("booking_days_ahead") == 14)
    check("limit o'zgardi", db.rule("max_active_bookings") == 5)
    check("dam olish kunlari o'zgardi", db.rule("weekend_days") == [5, 6])

    # Klinika
    await db.set_clinic("address", "Chilonzor 5-mavze, 12-uy")
    await db.set_clinic("map_link", "https://maps.example/xyz")
    check("manzil saqlandi", db.clinic()["address"] == "Chilonzor 5-mavze, 12-uy")
    check("havola saqlandi", db.clinic()["map_link"] == "https://maps.example/xyz")

    # Bo'lim nomi va soatlari
    check("nom o'zgartirildi", await db.update_department("treatment", name="🦷 Terapiya"))
    check("yangi nom o'qildi", db.dept_name("treatment") == "🦷 Terapiya")
    check("soatlar o'zgartirildi", await db.update_department("treatment", times=["08:00", "09:00"]))
    check("yangi soatlar", db.dept_times("treatment") == ["08:00", "09:00"])
    check("mavjud bo'lmagan bo'lim False", not await db.update_department("yoq", name="X"))

    # Yangi bo'lim
    key = await db.add_department("🦷 Implantatsiya", ["10:00", "11:00", "12:00"])
    check("yangi bo'lim qo'shildi", key in db.departments(), key)
    check("yangi bo'lim kaliti qisqa", len(key) <= 5, key)
    check("yangi bo'lim nomi", db.dept_name(key) == "🦷 Implantatsiya")
    check("endi 3 ta bo'lim", len(db.departments()) == 3)
    check("yangi bo'lim oxirida", list(db.departments())[-1] == key, str(list(db.departments())))

    key2 = await db.add_department("🦷 Ortodontiya", ["09:00"])
    check("ikkinchi yangi bo'lim boshqa kalit oldi", key2 != key, f"{key} vs {key2}")

    # callback_data 64 bayt limitiga sig'ishi kerak
    from callbacks import SlotCB
    packed = SlotCB(key=key2, date="2099-06-10", time="09:00").pack()
    check(f"yangi bo'lim callback'i sig'adi ({len(packed.encode())} bayt)", len(packed.encode()) <= 64)

    # Tartibni o'zgartirish
    keys = list(db.departments())
    await db.update_department_order(keys[-1], -1)
    check("tartib o'zgardi", list(db.departments())[0] == keys[-1], str(list(db.departments())))

    # O'chirish
    check("bo'lim o'chirildi", await db.delete_department(key2))
    check("o'chirilgan bo'lim yo'q", db.department(key2) is None)
    check("o'chirilgan bo'lim nomi xavfsiz qaytadi", isinstance(db.dept_name(key2), str))
    check("mavjud bo'lmaganni o'chirish False", not await db.delete_department("yoq"))

    # Oxirgi bo'limni o'chirib bo'lmaydi
    for k in list(db.departments())[:-1]:
        await db.delete_department(k)
    check("faqat 1 ta bo'lim qoldi", len(db.departments()) == 1)
    check("OXIRGI bo'limni o'chirib BO'LMAYDI",
          not await db.delete_department(list(db.departments())[0]))

    # Faol navbatlar hisobi
    await fresh_db()
    await db.save_user(555, "Ali", None, "+998901112233")
    await db.create_booking(555, "treatment", TREAT, FUTURE, "09:00")
    check("bo'limdagi faol navbat sanaldi", db.active_bookings_in_department("treatment") == 1)
    check("boshqa bo'limda 0", db.active_bookings_in_department("consultation") == 0)


async def test_settings_persistence_and_reset() -> None:
    print("\n📦 Sozlamalar: saqlanishi va tiklash")
    await fresh_db()

    await db.set_rule("booking_days_ahead", 21)
    await db.set_clinic("address", "Yangi manzil")
    new_key = await db.add_department("🦷 Test bo'lim", ["07:00", "08:00"])
    await db.change_admin_password("maxfiy-parol")
    await db.save_user(555, "Ali", None, "+998901112233")
    await db.close()

    # Botni "qayta ishga tushirish"
    await db.connect()
    check("qoida saqlanib qoldi", db.rule("booking_days_ahead") == 21)
    check("manzil saqlanib qoldi", db.clinic()["address"] == "Yangi manzil")
    check("yangi bo'lim saqlanib qoldi", db.department(new_key) is not None)
    check("bo'lim soatlari saqlanib qoldi", db.dept_times(new_key) == ["07:00", "08:00"])
    check("standart bo'limlar ustiga yozilmadi", db.rule("booking_days_ahead") != 7)

    # Standart holatga qaytarish
    await db.reset_settings()
    check("qoidalar tiklandi", db.rule("booking_days_ahead") == 7)
    check("manzil tiklandi", db.clinic()["address"] != "Yangi manzil")
    check("qo'shilgan bo'lim o'chdi", db.department(new_key) is None)
    check("standart bo'limlar qaytdi", len(db.departments()) == 2)
    check("PAROL tegilmadi", await db.verify_admin_password("maxfiy-parol"))
    check("BEMOR tegilmadi", await db.is_registered(555))


async def test_time_parsing() -> None:
    print("\n📦 Soatlarni o'qish (admin kiritadi)")
    from utils import parse_times

    cases = {
        "09:00, 10:30, 12:00": ["09:00", "10:30", "12:00"],
        "09:00 10:30 12:00": ["09:00", "10:30", "12:00"],
        "9:00,10:30": ["09:00", "10:30"],          # bir xonali soat to'ldiriladi
        "12:00, 09:00": ["09:00", "12:00"],        # tartiblanadi
        "09:00, 09:00, 10:00": ["09:00", "10:00"], # takror olib tashlanadi
        "09:00\n10:30": ["09:00", "10:30"],
        "23:59": ["23:59"],
        "00:00": ["00:00"],
        "24:00": None,   # noto'g'ri soat
        "09:60": None,   # noto'g'ri daqiqa
        "0900": None,
        "salom": None,
        "": None,
        "09:00, salom": None,
    }
    for raw, expected in cases.items():
        got = parse_times(raw)
        check(f"soatlar {raw!r:22} -> {expected}", got == expected, f"olindi: {got}")


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
        test_utils, test_admin_ids_parsing, test_backup_config, test_backup_encryption,
        test_backup_restore_logic, test_time_parsing,
        test_reminders, test_settings_storage, test_settings_persistence_and_reset,
        test_callbacks, test_password, test_admins,
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
