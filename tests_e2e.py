"""Uchidan-uchiga testlar: haqiqiy Update obyektlari Dispatcher orqali o'tkaziladi.

Telegram'ga HECH QANDAY so'rov ketmaydi — Bot sessiyasi soxta (MockSession) bilan
almashtirilgan, u yuborilgan xabarlarni ro'yxatga yig'adi.

Ishga tushirish:
    python tests_e2e.py
"""

import asyncio
import os
import sys
import tempfile
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import Any

_TMP = Path(tempfile.mkdtemp(prefix="navbat_e2e_"))
os.environ["BOT_TOKEN"] = "111111:TEST-TOKEN"
os.environ["DATA_FILE"] = str(_TMP / "data.json")
os.environ.setdefault("TIMEZONE", "Asia/Tashkent")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.methods import TelegramMethod  # noqa: E402
from aiogram.types import CallbackQuery, Chat, Contact, Message, Update, User  # noqa: E402

import config  # noqa: E402
import storage as db  # noqa: E402
from callbacks import AdminCB, AdminUserCB, DateCB, DeptCB, SlotCB, UserBookingCB  # noqa: E402
from handlers import setup_routers  # noqa: E402
from handlers.errors import on_error  # noqa: E402
from keyboards import BTN_ADMIN, BTN_BOOK, BTN_CANCEL, BTN_MY  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []

FUTURE = "2099-06-10"


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  ✅ {name}")
    else:
        FAILED.append(f"{name} — {detail}" if detail else name)
        print(f"  ❌ {name}  {detail}")


# --------------------------------------------------------------------------
# Soxta Telegram sessiyasi
# --------------------------------------------------------------------------

class MockSession(BaseSession):
    """Telegram API o'rniga ishlaydi: so'rovlarni yozib oladi, tarmoqqa chiqmaydi."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod] = []

    async def close(self) -> None:
        pass

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        yield b""

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout: int | None = None) -> Any:
        self.calls.append(method)
        name = type(method).__name__

        if name == "GetMe":
            return User(id=1, is_bot=True, first_name="TestBot", username="test_bot")
        if name in ("SendMessage", "EditMessageText", "EditMessageReplyMarkup"):
            return Message(
                message_id=len(self.calls) + 1000,
                date=datetime.now(),
                chat=Chat(id=getattr(method, "chat_id", 1) or 1, type="private"),
                text=getattr(method, "text", None) or "",
            )
        return True

    # --- testlar uchun yordamchilar ---

    def texts(self) -> list[str]:
        return [t for c in self.calls if (t := getattr(c, "text", None))]

    def last_text(self) -> str:
        return self.texts()[-1] if self.texts() else ""

    def alerts(self) -> list[str]:
        return [c.text or "" for c in self.calls if type(c).__name__ == "AnswerCallbackQuery"]

    def sent_to(self, chat_id: int) -> list[str]:
        return [c.text for c in self.calls
                if type(c).__name__ == "SendMessage" and c.chat_id == chat_id]

    def said(self, needle: str) -> bool:
        return any(needle.lower() in t.lower() for t in self.texts() + self.alerts())

    def deleted_messages(self) -> int:
        return sum(1 for c in self.calls if type(c).__name__ == "DeleteMessage")

    def reset(self) -> None:
        self.calls.clear()


# --------------------------------------------------------------------------
# Update yasovchilar
# --------------------------------------------------------------------------

_update_id = 0


def _next_id() -> int:
    global _update_id
    _update_id += 1
    return _update_id


def make_user(uid: int, name: str = "Test Bemor", username: str | None = None) -> User:
    first, _, last = name.partition(" ")
    return User(id=uid, is_bot=False, first_name=first, last_name=last or None, username=username)


def text_update(uid: int, text: str, name: str = "Test Bemor") -> Update:
    user = make_user(uid, name)
    return Update(
        update_id=_next_id(),
        message=Message(
            message_id=_next_id(),
            date=datetime.now(),
            chat=Chat(id=uid, type="private"),
            from_user=user,
            text=text,
        ),
    )


def contact_update(uid: int, phone: str, contact_owner: int | None = None, name: str = "Test Bemor") -> Update:
    user = make_user(uid, name)
    return Update(
        update_id=_next_id(),
        message=Message(
            message_id=_next_id(),
            date=datetime.now(),
            chat=Chat(id=uid, type="private"),
            from_user=user,
            contact=Contact(
                phone_number=phone,
                first_name=user.first_name,
                user_id=contact_owner if contact_owner is not None else uid,
            ),
        ),
    )


def callback_update(uid: int, data: str, name: str = "Test Bemor") -> Update:
    user = make_user(uid, name)
    return Update(
        update_id=_next_id(),
        callback_query=CallbackQuery(
            id=str(_next_id()),
            from_user=user,
            chat_instance="test-instance",
            data=data,
            message=Message(
                message_id=_next_id(),
                date=datetime.now(),
                chat=Chat(id=uid, type="private"),
                from_user=make_user(1, "TestBot"),
                text="oldingi xabar",
            ),
        ),
    )


# --------------------------------------------------------------------------

# Routerlar modul darajasidagi obyektlar — ularni faqat BIR MARTA ulash mumkin.
# Shuning uchun Dispatcher bir marta quriladi, har bir test uchun esa
# yangi Bot + MockSession + toza baza + toza FSM holati beriladi.
_dp: Dispatcher | None = None


async def build() -> tuple[Bot, Dispatcher, MockSession]:
    global _dp

    for suffix in ("", ".bak", ".tmp"):
        Path(str(config.DATA_PATH) + suffix).unlink(missing_ok=True)

    if _dp is None:
        _dp = Dispatcher(storage=MemoryStorage())
        _dp.include_router(setup_routers())
        _dp.errors.register(on_error)
    else:
        # oldingi testdan qolgan FSM holatlarini tozalash
        await _dp.fsm.storage.close()
        _dp.fsm.storage = MemoryStorage()

    session = MockSession()
    bot = Bot(token=config.BOT_TOKEN, session=session,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await db.connect()
    return bot, _dp, session


async def test_registration() -> None:
    print("\n📦 Ro'yxatdan o'tish")
    bot, dp, s = await build()

    await dp.feed_update(bot, text_update(555, "/start"))
    check("yangi foydalanuvchidan telefon so'raldi", s.said("telefon"))
    check("bazaga hali yozilmadi", not await db.is_registered(555))

    # Ro'yxatdan o'tmasdan navbat olishga urinish
    s.reset()
    await dp.feed_update(bot, text_update(555, BTN_BOOK))
    check("ro'yxatsiz navbat olib BO'LMAYDI", not s.said("Qaysi bo'limga"), s.last_text()[:60])
    check("qayta telefon so'raldi", s.said("telefon"))

    # Begona kontakt
    s.reset()
    await dp.feed_update(bot, contact_update(555, "+998901112233", contact_owner=999))
    check("BEGONA kontakt rad etildi", s.said("o'zingizning"))
    check("baza o'zgarmadi", not await db.is_registered(555))

    # Noto'g'ri qo'lda kiritilgan raqam
    s.reset()
    await dp.feed_update(bot, text_update(555, "12345"))
    check("noto'g'ri raqam rad etildi", s.said("noto'g'ri"))

    # To'g'ri qo'lda kiritish
    s.reset()
    await dp.feed_update(bot, text_update(555, "90 111 22 33"))
    check("qo'lda kiritilgan raqam qabul qilindi", s.said("saqlandi"), s.last_text()[:60])
    check("raqam normallashtirildi", (await db.get_user(555))["phone"] == "+998901112233",
          str(await db.get_user(555)))

    # Kontakt orqali
    s.reset()
    await dp.feed_update(bot, contact_update(666, "998901112244", name="Vali Aliyev"))
    check("kontakt orqali ro'yxatdan o'tdi", await db.is_registered(666))
    check("ism saqlandi", (await db.get_user(666))["full_name"] == "Vali Aliyev")

    await bot.session.close()


async def test_booking_flow() -> None:
    print("\n📦 Navbat olish jarayoni")
    bot, dp, s = await build()
    await db.save_user(555, "Ali Valiyev", "ali", "+998901112233")
    await db.save_user(666, "Vali Aliyev", None, "+998901112244")

    await dp.feed_update(bot, text_update(555, BTN_BOOK))
    check("bo'limlar ko'rsatildi", s.said("Qaysi bo'limga"))

    s.reset()
    await dp.feed_update(bot, callback_update(555, DeptCB(key="treatment").pack()))
    check("kunlar ko'rsatildi", s.said("Qaysi kunga"))

    s.reset()
    await dp.feed_update(bot, callback_update(555, DateCB(key="treatment", date=FUTURE).pack()))
    check("soatlar ko'rsatildi", s.said("qulay soatni"))

    s.reset()
    await dp.feed_update(bot, callback_update(555, SlotCB(key="treatment", date=FUTURE, time="09:00").pack()))
    check("navbat olindi", s.said("muvaffaqiyatli olindi"), s.last_text()[:80])
    check("bazada faol navbat bor", await db.count_active_bookings(555) == 1)

    # O'sha soatni boshqa bemor bosadi
    s.reset()
    await dp.feed_update(bot, callback_update(666, SlotCB(key="treatment", date=FUTURE, time="09:00").pack()))
    check("band soat boshqa bemorga berilmadi", s.said("band"), str(s.alerts()))
    check("ikkinchi navbat yaratilmadi", await db.count_active_bookings(666) == 0)

    # O'sha kunga ikkinchi navbat
    s.reset()
    await dp.feed_update(bot, callback_update(555, SlotCB(key="treatment", date=FUTURE, time="10:30").pack()))
    check("bir kunga ikkinchi navbat berilmadi", s.said("allaqachon"), str(s.alerts()))

    # O'tib ketgan vaqt
    s.reset()
    await dp.feed_update(bot, callback_update(666, SlotCB(key="treatment", date="2020-01-01", time="09:00").pack()))
    check("o'tgan sanaga navbat berilmadi", s.said("o'tib ketgan"), str(s.alerts()))

    # Mening navbatim
    s.reset()
    await dp.feed_update(bot, text_update(555, BTN_MY))
    check("navbat ro'yxatda ko'rindi", s.said("09:00") and s.said("faol navbat"))

    s.reset()
    await dp.feed_update(bot, text_update(666, BTN_MY))
    check("navbatsiz bemorga bo'sh javob", s.said("faol navbat yo'q"))

    await bot.session.close()


async def test_cancel_ownership() -> None:
    print("\n📦 Bekor qilish va EGALIK tekshiruvi")
    bot, dp, s = await build()
    await db.save_user(555, "Ali", None, "+998901112233")
    await db.save_user(666, "Vali", None, "+998901112244")
    app_id = await db.create_booking(555, "treatment", "🦷 Davolash bo'limi", FUTURE, "09:00")

    # ⚠️ Eski kodda AYNAN shu hujum ishlagan: begona odam del_<id> yuborib o'chirardi
    s.reset()
    await dp.feed_update(bot, callback_update(666, UserBookingCB(action="ask", id=app_id).pack()))
    check("begona odamga navbat ma'lumoti BERILMADI", s.said("sizga tegishli emas"), str(s.alerts()))

    s.reset()
    await dp.feed_update(bot, callback_update(666, UserBookingCB(action="yes", id=app_id).pack()))
    check("begona odam bekor qila OLMADI", s.said("sizga tegishli emas"), str(s.alerts()))
    check("navbat hali ham faol", (await db.get_booking(app_id))["status"] == "active")

    # Egasi
    s.reset()
    await dp.feed_update(bot, text_update(555, BTN_CANCEL))
    check("egasiga ro'yxat ko'rsatildi", s.said("Qaysi navbatni"))

    s.reset()
    await dp.feed_update(bot, callback_update(555, UserBookingCB(action="ask", id=app_id).pack()))
    check("tasdiqlash so'raldi", s.said("Rostdan bekor"))

    s.reset()
    await dp.feed_update(bot, callback_update(555, UserBookingCB(action="yes", id=app_id).pack()))
    check("egasi bekor qildi", s.said("bekor qilindi"))
    check("status cancelled", (await db.get_booking(app_id))["status"] == "cancelled")
    check("soat bo'shadi", await db.booked_times("treatment", FUTURE) == set())

    await bot.session.close()


async def test_admin_login() -> None:
    print("\n📦 Admin paneliga parol bilan kirish")
    bot, dp, s = await build()

    await dp.feed_update(bot, text_update(100, "/admin", name="Jasurbek Admin"))
    check("parol so'raldi", s.said("Parolni yuboring"))
    check("hali admin emas", not await db.is_admin(100))

    # Xato parol
    s.reset()
    await dp.feed_update(bot, text_update(100, "qwerty"))
    check("xato parol rad etildi", s.said("noto'g'ri"))
    check("qolgan urinishlar ko'rsatildi", s.said("4"))
    check("parol xabari chatdan O'CHIRILDI", s.deleted_messages() == 1)
    check("xato paroldan keyin admin emas", not await db.is_admin(100))

    # To'g'ri parol
    s.reset()
    await dp.feed_update(bot, text_update(100, "1234567890", name="Jasurbek Admin"))
    check("BIRINCHI kirgan odam SUPER admin bo'ldi", s.said("super admin"), s.last_text()[:80])
    check("bazada super admin", await db.is_super_admin(100))
    check("parol xabari o'chirildi", s.deleted_messages() == 1)
    check("panel ochildi", s.said("Admin panel"))
    check("parolni almashtirish eslatildi", s.said("parolni almashtiring"))

    # Ikkinchi odam
    s.reset()
    await dp.feed_update(bot, text_update(200, "/admin", name="Ikkinchi Admin"))
    await dp.feed_update(bot, text_update(200, "1234567890", name="Ikkinchi Admin"))
    check("2-odam ODDIY admin bo'ldi", await db.is_admin(200) and not await db.is_super_admin(200))
    check("super adminga xabar ketdi", any("yangi admin" in t.lower() for t in s.sent_to(100)),
          str(s.sent_to(100))[:120])

    # Allaqachon admin -> parol so'ralmaydi
    s.reset()
    await dp.feed_update(bot, text_update(100, BTN_ADMIN, name="Jasurbek Admin"))
    check("mavjud admindan parol so'ralmadi", not s.said("Parolni yuboring"))
    check("panel darhol ochildi", s.said("Admin panel"))

    await bot.session.close()


async def test_admin_bruteforce() -> None:
    print("\n📦 Parolni tanlashdan himoya (brute-force)")
    bot, dp, s = await build()

    await dp.feed_update(bot, text_update(300, "/admin"))
    for i in range(5):
        await dp.feed_update(bot, text_update(300, f"xato-parol-{i}"))

    check("5 urinishdan keyin bloklandi", s.said("bloklandingiz"), s.last_text()[:80])
    check("admin bo'lib qolmadi", not await db.is_admin(300))

    s.reset()
    await dp.feed_update(bot, text_update(300, "/admin"))
    check("blok davrida kirishga ruxsat yo'q", s.said("daqiqadan keyin"), s.last_text()[:80])

    s.reset()
    await dp.feed_update(bot, text_update(300, "1234567890"))
    check("blokdan keyin to'g'ri parol ham qabul qilinmadi", not await db.is_admin(300))

    await bot.session.close()


async def test_admin_management() -> None:
    print("\n📦 Adminlarni boshqarish")
    bot, dp, s = await build()

    await db.add_admin(100, "Super Admin", "sup")
    await db.add_admin(200, "Oddiy Admin", "odd", added_by=100)
    await db.add_admin(300, "Uchinchi", None, added_by=100)

    # Ro'yxat
    s.reset()
    await dp.feed_update(bot, callback_update(100, AdminCB(action="admins").pack()))
    check("adminlar ro'yxati ko'rindi", s.said("Adminlar ro'yxati"))
    check("super admin ko'rsatildi", s.said("Super Admin"))
    check("oddiy admin ko'rsatildi", s.said("Oddiy Admin"))
    check("darajalar ko'rsatildi", s.said("Super admin") and s.said("👑"))
    check("ID lar ko'rsatildi", s.said("100") and s.said("200"))
    check("'siz' belgisi qo'yildi", s.said("siz"))

    # Oddiy admin ro'yxatni ko'radi, lekin boshqara olmaydi
    s.reset()
    await dp.feed_update(bot, callback_update(200, AdminCB(action="admins").pack()))
    check("oddiy admin ham ro'yxatni ko'radi", s.said("Adminlar ro'yxati"))
    check("unga boshqarish mumkin emasligi aytildi", s.said("faqat super admin"))

    # Oddiy admin boshqasini chiqarmoqchi
    s.reset()
    await dp.feed_update(bot, callback_update(200, AdminUserCB(action="del_yes", user_id=300).pack()))
    check("oddiy admin boshqasini chiqara OLMADI", s.said("faqat super admin"), str(s.alerts()))
    check("uchinchi admin joyida", await db.is_admin(300))

    # Super admin chiqaradi
    s.reset()
    await dp.feed_update(bot, callback_update(100, AdminUserCB(action="del_ask", user_id=300).pack()))
    check("tasdiqlash so'raldi", s.said("chiqarasizmi"))

    s.reset()
    await dp.feed_update(bot, callback_update(100, AdminUserCB(action="del_yes", user_id=300).pack()))
    check("SUPER admin adminni chiqardi", not await db.is_admin(300))
    check("chiqarilganiga xabar berildi", s.said("chiqarildi"))
    check("chiqarilgan odamga xabar ketdi", any("chiqarildingiz" in t for t in s.sent_to(300)),
          str(s.sent_to(300)))
    check("ro'yxat yangilandi", s.said("Adminlar ro'yxati"))

    # Super adminni chiqarishga urinish
    s.reset()
    await dp.feed_update(bot, callback_update(100, AdminUserCB(action="del_yes", user_id=100).pack()))
    check("SUPER adminni chiqarib bo'lmadi", await db.is_admin(100))

    # Super admin o'zi chiqmoqchi
    s.reset()
    await dp.feed_update(bot, callback_update(100, AdminCB(action="logout").pack()))
    check("super admin o'zi ham chiqa olmaydi", s.said("o'zini ro'yxatdan chiqara olmaydi"), str(s.alerts()))

    # Oddiy admin chiqadi
    s.reset()
    await dp.feed_update(bot, callback_update(200, AdminCB(action="logout").pack()))
    check("oddiy admindan tasdiq so'raldi", s.said("voz kechasizmi"))
    await dp.feed_update(bot, callback_update(200, AdminCB(action="logout_yes").pack()))
    check("oddiy admin chiqdi", not await db.is_admin(200))

    await bot.session.close()


async def test_password_change() -> None:
    print("\n📦 Parolni o'zgartirish (faqat super admin)")
    bot, dp, s = await build()
    await db.add_admin(100, "Super", None)
    await db.add_admin(200, "Oddiy", None, added_by=100)

    # Oddiy admin urinadi
    s.reset()
    await dp.feed_update(bot, callback_update(200, AdminCB(action="passwd").pack()))
    check("oddiy admin parolni o'zgartira OLMAYDI", s.said("faqat super admin"), str(s.alerts()))

    # Super admin
    s.reset()
    await dp.feed_update(bot, callback_update(100, AdminCB(action="passwd").pack()))
    check("yangi parol so'raldi", s.said("Yangi parolni yuboring"))

    # Juda qisqa
    s.reset()
    await dp.feed_update(bot, text_update(100, "ab"))
    check("qisqa parol rad etildi", s.said("kamida"))
    check("parol xabari o'chirildi", s.deleted_messages() == 1)

    # Boshlang'ich parolni qayta tanlash
    s.reset()
    await dp.feed_update(bot, text_update(100, "1234567890"))
    check("boshlang'ich parolni qayta tanlab bo'lmaydi", s.said("boshlang'ich parol"))

    # To'g'ri parol
    s.reset()
    await dp.feed_update(bot, text_update(100, "Maxfiy-Parol-2026"))
    check("parol o'zgartirildi", s.said("muvaffaqiyatli o'zgartirildi"), s.last_text()[:80])
    check("yangi parol ishlaydi", await db.verify_admin_password("Maxfiy-Parol-2026"))
    check("eski parol ishlamaydi", not await db.verify_admin_password("1234567890"))
    check("boshqa adminlarga xabar berildi", any("parol" in t.lower() for t in s.sent_to(200)),
          str(s.sent_to(200)))
    check("parol chatda qolmadi", s.deleted_messages() == 1)
    check("panel qayta ochildi", s.said("Admin panel"))

    # Yangi parol bilan uchinchi odam kiradi
    s.reset()
    await dp.feed_update(bot, text_update(400, "/admin"))
    await dp.feed_update(bot, text_update(400, "Maxfiy-Parol-2026"))
    check("yangi parol bilan kirish ishladi", await db.is_admin(400))

    await bot.session.close()


async def test_admin_queue() -> None:
    print("\n📦 Admin panelida navbatlarni boshqarish")
    bot, dp, s = await build()
    await db.add_admin(100, "Super", None)
    await db.save_user(555, "Ali <script> Valiyev", "ali", "+998901112233")
    app_id = await db.create_booking(555, "treatment", "🦷 Davolash bo'limi", FUTURE, "09:00")

    s.reset()
    await dp.feed_update(bot, callback_update(100, AdminCB(action="queue", page=0).pack()))
    check("navbatlar ro'yxati ko'rindi", s.said("Kutilayotgan navbatlar"))
    check("bemor ma'lumoti ko'rindi", s.said("+998901112233"))
    check("HTML xavfsiz (escaping ishladi)", s.said("&lt;script&gt;"), s.last_text()[:160])

    # Bemorni chaqirish
    s.reset()
    from callbacks import AdminQueueCB
    await dp.feed_update(bot, callback_update(100, AdminQueueCB(action="notify", id=app_id, page=0).pack()))
    check("bemorga chaqiruv yuborildi", any("NAVBATINGIZ KELDI" in t for t in s.sent_to(555)),
          str(s.sent_to(555))[:100])

    # Oddiy foydalanuvchi admin panelga kira olmaydi
    s.reset()
    await dp.feed_update(bot, callback_update(999, AdminCB(action="queue", page=0).pack()))
    check("begona odam admin panelga kira OLMADI", s.said("ruxsatingiz yo'q"), str(s.alerts()))
    check("begona odamga ma'lumot ko'rsatilmadi", not s.said("+998901112233"))

    # "Keldi" deb belgilash
    s.reset()
    await dp.feed_update(bot, callback_update(100, AdminQueueCB(action="done", id=app_id, page=0).pack()))
    check("'keldi' belgilandi", (await db.get_booking(app_id))["status"] == "done")

    # Admin navbatni bekor qiladi
    app2 = await db.create_booking(555, "treatment", "🦷 Davolash bo'limi", FUTURE, "10:30")
    s.reset()
    await dp.feed_update(bot, callback_update(100, AdminQueueCB(action="cancel", id=app2, page=0).pack()))
    check("admin navbatni bekor qildi", (await db.get_booking(app2))["status"] == "cancelled")
    check("bemorga xabar berildi", any("bekor qilindi" in t for t in s.sent_to(555)), str(s.sent_to(555))[:120])

    # Statistika
    s.reset()
    await dp.feed_update(bot, callback_update(100, AdminCB(action="stats").pack()))
    check("statistika ko'rindi", s.said("Statistika") and s.said("bemorlar"))

    await bot.session.close()


async def test_notifications() -> None:
    print("\n📦 Adminlarga bildirishnomalar")
    bot, dp, s = await build()
    await db.add_admin(100, "Super", None)
    await db.add_admin(200, "Oddiy", None, added_by=100)
    await db.save_user(555, "Ali Valiyev", None, "+998901112233")

    s.reset()
    await dp.feed_update(bot, callback_update(555, SlotCB(key="treatment", date=FUTURE, time="09:00").pack()))
    check("1-adminga yangi navbat haqida xabar ketdi",
          any("Yangi navbat" in t for t in s.sent_to(100)), str(s.sent_to(100))[:100])
    check("2-adminga ham xabar ketdi", any("Yangi navbat" in t for t in s.sent_to(200)))
    check("bemorga admin xabari ketmadi", not any("Yangi navbat" in t for t in s.sent_to(555)))

    await bot.session.close()


async def test_fallback_and_errors() -> None:
    print("\n📦 Noma'lum xabarlar va xatolar")
    bot, dp, s = await build()
    await db.save_user(555, "Ali", None, "+998901112233")

    s.reset()
    await dp.feed_update(bot, text_update(555, "salom qalaysiz"))
    check("noma'lum matnga javob berildi", s.said("tushunmadim"), s.last_text()[:60])

    s.reset()
    await dp.feed_update(bot, callback_update(555, "eski_tugma_12345"))
    check("eskirgan tugmaga javob berildi", s.said("eskirgan"), str(s.alerts()))

    s.reset()
    await dp.feed_update(bot, text_update(555, "/help"))
    check("/help ishladi", s.said("Bot imkoniyatlari"))

    s.reset()
    await dp.feed_update(bot, text_update(555, "/cancel"))
    check("/cancel ishladi", s.said("menyu") or s.said("bekor"))

    await bot.session.close()


async def main() -> None:
    print("=" * 62)
    print("  Bot_navbat — uchidan-uchiga (E2E) testlar")
    print("=" * 62)

    for test in (
        test_registration, test_booking_flow, test_cancel_ownership,
        test_admin_login, test_admin_bruteforce, test_admin_management,
        test_password_change, test_admin_queue, test_notifications,
        test_fallback_and_errors,
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
    import logging
    logging.disable(logging.CRITICAL)
    asyncio.run(main())
