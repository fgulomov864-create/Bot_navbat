# 🦷 Bot_navbat — stomatologiya klinikasi uchun navbat boti

Telegram bot: bemorlar bo'lim, kun va soatni tanlab onlayn navbat oladi;
shifokor/administrator esa parol bilan himoyalangan panel orqali navbatlarni boshqaradi.

**Texnologiyalar:** Python 3.11+ · [aiogram 3](https://docs.aiogram.dev) · JSON saqlash (tashqi baza kerak emas)

---

## Imkoniyatlar

### Bemor uchun
| Tugma | Vazifasi |
|---|---|
| 📅 Navbat olish | Bo'lim → kun → soat. Band soatlar ❌, o'tib ketganlari ⌛ bilan belgilanadi |
| 📋 Mening navbatim | Faol navbatlar ro'yxati |
| ❌ Navbatni bekor qilish | Tasdiqlash bilan; soat darhol boshqalarga bo'shaydi |
| 📍 Manzil / Lokatsiya | Google Maps havolasi |

Telefon raqamini tugma orqali ham, qo'lda ham kiritish mumkin (`+998901234567`,
`998901234567`, `901234567` — hammasi qabul qilinadi).

### Admin uchun — `/admin`

Panelga **parol** bilan kiriladi. Boshlang'ich parol: `1234567890`.

> **Parolni to'g'ri kiritgan BIRINCHI odam — SUPER ADMIN bo'ladi.**
> Faqat u parolni o'zgartira oladi va adminlarni ro'yxatdan chiqara oladi.

| Menyu | Kim ko'radi | Vazifasi |
|---|---|---|
| 📋 Navbatlar | hamma admin | Sahifalangan ro'yxat: 🚨 chaqirish · ✅ keldi · 🚫 kelmadi · ❌ bekor qilish |
| 📊 Statistika | hamma admin | Bemorlar, bugungi/kutilayotgan navbatlar, haftalik hisobot |
| 👥 Adminlar ro'yxati | hamma admin | Kim admin, kim super admin, ID va qo'shilgan sana |
| ❌ *Adminni chiqarish* | **faqat super admin** | Ro'yxatdagi oddiy adminni o'chirish (tasdiqlash bilan) |
| 🔑 Parolni o'zgartirish | **faqat super admin** | Yangi parol; barcha adminlarga xabar boradi |
| 🚪 Adminlikdan chiqish | oddiy admin | O'z admin huquqidan voz kechish |

**Xavfsizlik choralari:**
- Parol bazada ochiq saqlanmaydi — `PBKDF2-SHA256`, 200 000 iteratsiya, tasodifiy salt.
- Parol yozilgan xabar chatdan **darhol o'chiriladi**.
- 5 marta xato kiritilsa — 15 daqiqaga blok.
- Super adminni hech kim (o'zi ham) ro'yxatdan chiqara olmaydi — aks holda parolni
  o'zgartiradigan odam qolmasdi.

---

## O'rnatish

```bash
git clone https://github.com/Jasurbek09/Bot_navbat.git
cd Bot_navbat

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env             # va ichini to'ldiring
python main.py
```

### `.env` sozlamalari

| O'zgaruvchi | Majburiy | Izoh |
|---|---|---|
| `BOT_TOKEN` | ✅ | @BotFather dan olinadi |
| `ADMIN_ID` | ❌ | Ko'rsatilsa — avtomatik super admin. Bo'sh bo'lsa, birinchi kirgan odam super admin bo'ladi |
| `ADMIN_PASSWORD` | ❌ | Boshlang'ich parol (default: `1234567890`) |
| `TIMEZONE` | ❌ | Default: `Asia/Tashkent` |
| `DATA_FILE` | ❌ | Default: `data.json` |
| `CLINIC_ADDRESS`, `MAP_LINK` | ❌ | Manzil va xarita havolasi |

> ⚠️ `.env` va `data.json` **hech qachon** git'ga qo'shilmasin — ular tokeningizni va
> bemorlarning shaxsiy ma'lumotlarini saqlaydi. `.gitignore` da bloklangan.

---

## Eski SQLite bazasidan ko'chirish

Loyiha avval SQLite (`dental_bot.db`) ishlatgan. Ma'lumotlarni ko'chirish uchun:

```bash
python migrate_to_json.py                  # dental_bot.db -> data.json
python migrate_to_json.py eski.db yangi.json
```

Skript eski `.db` faylga tegmaydi (faqat o'qiydi) va uchala eski sxemani ham tushunadi.

---

## Loyiha tuzilishi

```
main.py              Kirish nuqtasi: logging, Bot/Dispatcher, startup/shutdown
config.py            .env o'qish, konstantalar, bo'limlar va ish soatlari
storage.py           JSON ma'lumotlar qatlami (indekslar, atomar yozish, parol hash)
migrate_to_json.py   SQLite -> JSON konvertori
utils.py             Vaqt zonasi, sana formatlash, HTML escaping
keyboards.py         Barcha klaviaturalar
callbacks.py         Tipli callback_data fabrikalari
services.py          Xabar yuborish, adminlarga bildirishnoma
handlers/
  common.py          /start, ro'yxatdan o'tish, manzil
  booking.py         Navbat olish / ko'rish / bekor qilish
  admin.py           Admin panel: parol, navbatlar, adminlar
  fallback.py        Tushunilmagan xabarlar
  errors.py          Global xato ushlagich
tests.py             Biznes-mantiq testlari (134 ta)
tests_e2e.py         Uchidan-uchiga testlar (97 ta)
```

### Ma'lumotlar saqlanishi

Hamma narsa bitta `data.json` faylida:

```jsonc
{
  "version": 2,
  "settings":     { "admin_password": "pbkdf2_sha256$200000$..." },
  "users":        { "7437501484": { "user_id": …, "full_name": …, "phone": … } },
  "admins":       { "637554472":  { "is_super": true, "added_by": null, … } },
  "appointments": [ { "id": 1, "service_key": "treatment", "status": "active", … } ],
  "next_id": 2
}
```

Fayl ishga tushganda **to'liq xotiraga** yuklanadi, shuning uchun barcha o'qish
amallari diskka murojaat qilmaydi. Tezlik uchun 3 ta indeks yuritiladi:
`id → navbat`, `user_id → navbatlar`, `(bo'lim, kun, soat) → navbat`.

Yozishda:
- barcha o'zgartirishlar `asyncio.Lock` ichida — bir vaqtda ikki bemor yozsa ham fayl buzilmaydi;
- yozish **atomar** (`.tmp` ga yozib, `os.replace`) — jarayon uzilsa ham eski fayl butun qoladi;
- har safar `.bak` zaxira nusxasi yangilanadi, fayl buzilsa undan avtomatik tiklanadi.

---

## Testlar

```bash
python tests.py        # biznes-mantiq: 134 ta test
python tests_e2e.py    # handlerlar: 97 ta test
```

E2E testlar Telegram'ga **ulanmaydi** — Bot sessiyasi soxta obyekt bilan
almashtirilgan, u yuborilgan xabarlarni ro'yxatga yig'adi.

Testlar quyidagilarni tekshiradi: ro'yxatdan o'tish, navbat olish, bandlik,
egalik tekshiruvi, admin parol oqimi, brute-force bloki, adminlarni boshqarish,
50 ta bir vaqtdagi bron urinishi, fayl buzilgandan keyin tiklanish,
SQLite→JSON migratsiyasi.

---

## Sozlash

Ish soatlari va bo'limlar — [config.py](config.py) dagi `DEPARTMENTS`:

```python
DEPARTMENTS = {
    "treatment":    {"name": "🦷 Davolash bo'limi", "times": ["09:00", "10:30", …]},
    "consultation": {"name": "👨‍⚕️ Maslahat olish",  "times": ["09:30", "11:00", …]},
}
```

Boshqa sozlamalar: `BOOKING_DAYS_AHEAD` (necha kun oldindan), `MAX_ACTIVE_BOOKINGS`
(bir bemordagi navbat limiti), `MIN_LEAD_MINUTES` (qabulgacha minimal vaqt),
`WEEKEND_DAYS` (dam olish kunlari), `ADMIN_PAGE_SIZE`.

---

## Ma'lum cheklovlar

- **Avtomatik eslatma yo'q** — bemorni chaqirish admin tugmasi orqali qo'lda bajariladi.
  Rejalashtirilgan: `apscheduler` bilan qabuldan 1 kun/1 soat oldin eslatma.
- **Bitta jarayon** — JSON saqlash bir vaqtda bitta bot nusxasiga mo'ljallangan.
  Bir nechta nusxada (horizontal scaling) ishlatish uchun PostgreSQL kerak bo'ladi.
- Ko'p tillilik yo'q (faqat o'zbekcha).

Batafsil ro'yxat: [Task.md](Task.md)
