# 🦷 Bot_navbat — stomatologiya klinikasi uchun navbat boti

Telegram bot: bemorlar bo'lim, kun va soatni tanlab onlayn navbat oladi;
shifokor/administrator esa parol bilan himoyalangan panel orqali navbatlarni boshqaradi.

**Texnologiyalar:** Python 3.11+ · [aiogram 3](https://docs.aiogram.dev) · JSON saqlash
(tashqi ma'lumotlar bazasi kerak emas — SQLite ham, PostgreSQL ham)

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
| 🚪 Adminlikdan chiqish | **faqat oddiy admin** | O'z admin huquqidan voz kechish |
| ⚙️ Sozlamalar | **faqat super admin** | Bo'limlar, ish soatlari, qoidalar, manzil |
| 👥 Adminlar ro'yxati | **faqat super admin** | Kim admin, ID, daraja, sana + ❌ ro'yxatdan chiqarish |
| 🔑 Parolni o'zgartirish | **faqat super admin** | Yangi parol; barcha adminlarga xabar boradi |
| 💾 Hozir zaxiralash | **faqat super admin** | data.json ni darhol GitHub'ga yuklaydi |

> Oddiy adminda super admin tugmalari **umuman chizilmaydi**. Tugma yo'q bo'lsa ham
> callback'ni qo'lda yuborish mumkin, shuning uchun har bir amal **serverda ham**
> qayta tekshiriladi.

### ⚙️ Sozlamalar — hammasi paneldan o'zgartiriladi

Ish soatlarini yoki manzilni o'zgartirish uchun **kodga tegish va qayta deploy
qilish kerak emas**. Super admin panelda o'zgartiradi — bemorlar darhol ko'radi.

| Bo'lim | Nimani o'zgartirish mumkin |
|---|---|
| 🏥 Bo'limlar va soatlar | Bo'lim qo'shish/o'chirish, nomini va ish soatlarini o'zgartirish, tartibini almashtirish |
| 📅 Navbat qoidalari | Necha kun oldindan yozilish · bemorga navbat limiti · qabulgacha minimal vaqt · dam olish kunlari |
| 📍 Klinika ma'lumotlari | Manzil matni va Google Maps havolasi |
| 🔔 Eslatmalar | Kun oldin / soat oldin avtomatik eslatmani yoqish-o'chirish |
| ♻️ Standart holatga qaytarish | Sozlamalarni boshlang'ich holatga qaytaradi (bemorlar, navbatlar, adminlar va parol **tegilmaydi**) |

Soatlar oddiy matn bilan kiritiladi — `09:00, 10:30, 12:00`. Bot `9:00` ni ham
tushunadi, takrorlarni olib tashlaydi va tartiblaydi. Noto'g'ri qiymat saqlanmaydi.

`config.py` dagi `DEFAULT_*` qiymatlari faqat **birinchi ishga tushishda** ishlatiladi —
undan keyin manba `data.json` bo'ladi.

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
| `ADMIN_ID` | ❌ | Super adminlar **ro'yxati**. Bo'sh bo'lsa, birinchi kirgan odam super admin bo'ladi |
| `ADMIN_PASSWORD` | ❌ | Boshlang'ich parol (default: `1234567890`) |
| `TIMEZONE` | ❌ | Default: `Asia/Tashkent` |
| `DATA_FILE` | ❌ | Default: `data.json`. Railway'da: `/data/data.json` |
| `CLINIC_ADDRESS`, `MAP_LINK` | ❌ | Manzil va xarita havolasi |
| `BACKUP_REPO`, `BACKUP_TOKEN` | ❌ | GitHub zaxirasi — pastga qarang |
| `BACKUP_BRANCH` | ❌ | Default `main`. Railway bilan **`backup`** qiling |
| `BACKUP_ENCRYPT_KEY` | ❌ | Public repo'ga zaxiralasangiz — **majburiy** |

`ADMIN_ID` bir nechta odamni qabul qiladi, hamma format ishlaydi:

```bash
ADMIN_ID=[]                        # hech kim — parol bilan kiriladi
ADMIN_ID=637554472                 # bitta super admin
ADMIN_ID=[637554472, 123456789]    # ikkita super admin
ADMIN_ID=637554472,123456789       # xuddi shunday
```

> ⚠️ `.env` va `data.json` **hech qachon** git'ga qo'shilmasin — ular tokeningizni va
> bemorlarning shaxsiy ma'lumotlarini saqlaydi. `.gitignore` da bloklangan.

---

## 🚂 Railway'ga joylash

> 📄 Qadamma-qadam qo'llanma: **[DEPLOY.md](DEPLOY.md)**
> Tekshirish: `python check.py`

⚠️ **Eng muhim narsa:** Railway konteynerining diski **vaqtinchalik**. Hech narsa
qilinmasa, har bir redeploy'da `data.json` — ya'ni **barcha bemorlar va navbatlar** —
o'chib ketadi. Quyidagi ikki himoyani ishlatish kerak.

### 1-qadam. Loyihani ulash

1. [railway.com](https://railway.com) → **New Project** → **Deploy from GitHub repo**
2. Shu repozitoriyni tanlang. `Dockerfile` va `railway.json` allaqachon tayyor.

### 2-qadam. Volume — ma'lumot yo'qolmasligining ASOSIY kafolati

1. Service → **Settings** → **Volumes** → **Add Volume**
2. Mount path: `/data`
3. Variables bo'limiga qo'shing: `DATA_FILE=/data/data.json`

Volume — Railway'ning doimiy diski. Redeploy, restart, crash — ma'lumot joyida qoladi.

### 3-qadam. Variables

```bash
BOT_TOKEN=<@BotFather dan>
DATA_FILE=/data/data.json
ADMIN_ID=[637554472]
ADMIN_PASSWORD=<kuchli parol>
TIMEZONE=Asia/Tashkent
```

### 4-qadam. GitHub zaxirasi (qo'shimcha himoya)

Volume ham buzilishi yoki xato bilan o'chirilishi mumkin. Bot `data.json` ni
davriy ravishda GitHub'ga yuklab turadi va **ishga tushganda baza bo'sh bo'lsa,
o'sha zaxiradan avtomatik tiklaydi**.

> 🔒 **Zaxirada bemorlarning ismi va telefon raqami bo'ladi.** Shuning uchun
> ikki rejimdan biri talab qilinadi:
> - **private repo** — oddiy JSON yoziladi;
> - **public repo** — `BACKUP_ENCRYPT_KEY` majburiy, fayl shifrlanadi.
>
> Kalitsiz public repo aniqlansa, bot zaxiralashni **o'zi o'chiradi**.

> ⚠️ **Zaxira `main` shoxiga yozilmasin!** Railway `main` ga har push'da qayta
> deploy qiladi: zaxira → deploy → bot qayta ishga tushadi → yana zaxira →
> cheksiz sikl. Shuning uchun `BACKUP_BRANCH=backup` ishlatiladi
> (shox bo'lmasa, bot uni o'zi yaratadi).

1. Token oling: [github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens)
   - *Repository access* → faqat kerakli repo
   - *Permissions* → **Contents: Read and write**
2. Shifrlash kaliti yarating (public repo uchun majburiy):

```bash
python -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(48)))"
```

3. Railway Variables:

```bash
BACKUP_REPO=foydalanuvchi/repo
BACKUP_TOKEN=github_pat_...
BACKUP_BRANCH=backup           # main EMAS!
BACKUP_ENCRYPT_KEY=<yuqoridagi kalit>
BACKUP_INTERVAL_MINUTES=5      # ixtiyoriy
```

⚠️ **Shifr kalitini yo'qotmang** — yo'qolsa, zaxirani hech kim ocholmaydi.
Zaxirani qo'lda ochish: `python backup.py --decrypt backup.enc data.json`

### Ma'lumot qayerdan qaytadi

Ishga tushganda lokal fayl va zaxira solishtiriladi — **`revision` raqami
kattarog'i yutadi**:

| Holat | Natija |
|---|---|
| Lokal yo'q yoki bo'sh | GitHub'dan tiklanadi |
| GitHub'da zaxira yo'q | Lokal qoladi |
| GitHub yangiroq | GitHub'dan tiklanadi, lokal `.before-restore.bak` ga saqlanadi |
| Lokal yangiroq yoki teng | Lokal qoladi |
| Zaxira buzilgan / kalit noto'g'ri | Lokal qoladi, ma'lumot buzilmaydi |

Zaxira qachon yuboriladi:
- har `BACKUP_INTERVAL_MINUTES` daqiqada — **faqat ma'lumot o'zgargan bo'lsa**
  (keraksiz commit yaratilmaydi);
- bot to'xtatilayotganda (Railway redeploy'dan oldin `SIGTERM` yuboradi);
- super admin **💾 Hozir zaxiralash** tugmasini bosganda.

Zaxira holati admin panelining yuqorisida ko'rinib turadi: `💾 Zaxira: ✅ 15.09.2026 18:40`

---

## Loyiha tuzilishi

```
main.py              Kirish nuqtasi: logging, Bot/Dispatcher, startup/shutdown
config.py            .env o'qish, konstantalar, bo'limlar va ish soatlari
storage.py           Ma'lumotlar qatlami: JSON + indekslar, atomar yozish, parol hash
backup.py            GitHub'ga zaxiralash, shifrlash, tiklash
reminders.py         🔔 Avtomatik eslatmalar (kun oldin / soat oldin)
check.py             Deploy oldidan tekshiruv (nima tayyor, nima yetishmayapti)
utils.py             Vaqt zonasi, sana formatlash, HTML escaping
keyboards.py         Barcha klaviaturalar
callbacks.py         Tipli callback_data fabrikalari
services.py          Xabar yuborish, adminlarga bildirishnoma
handlers/
  common.py          /start, ro'yxatdan o'tish, manzil
  booking.py         Navbat olish / ko'rish / bekor qilish
  admin.py           Admin panel: parol, navbatlar, adminlar
  settings.py        ⚙️ Sozlamalar: bo'limlar, soatlar, qoidalar, klinika
  fallback.py        Tushunilmagan xabarlar
  errors.py          Global xato ushlagich
tests.py             Biznes-mantiq testlari (255 ta)
tests_e2e.py         Uchidan-uchiga testlar (153 ta)
Dockerfile           Railway / har qanday konteyner uchun
railway.json         Railway build va deploy sozlamalari
.github/workflows/   CI: har push'da lint + testlar
```

### Ma'lumotlar saqlanishi

Hamma narsa bitta `data.json` faylida:

```jsonc
{
  "version": 2,
  "settings": {
    "admin_password": "pbkdf2_sha256$200000$...",
    "departments": { "treatment": { "name": "🦷 Davolash bo'limi", "times": [...], "order": 0 } },
    "rules":    { "booking_days_ahead": 7, "max_active_bookings": 3, "weekend_days": [6] },
    "clinic":   { "address": "...", "map_link": "..." }
  },
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
python tests.py        # biznes-mantiq: 255 ta test
python tests_e2e.py    # handlerlar: 153 ta test
```

E2E testlar Telegram'ga **ulanmaydi** — Bot sessiyasi soxta obyekt bilan
almashtirilgan, u yuborilgan xabarlarni ro'yxatga yig'adi.

Testlar quyidagilarni tekshiradi: ro'yxatdan o'tish, navbat olish, bandlik,
egalik tekshiruvi, admin parol oqimi, brute-force bloki, adminlarni boshqarish,
**menyu ko'rinishi** (oddiy admin super admin bo'limlarini ko'rmasligi),
`ADMIN_ID` ro'yxatini o'qish, **sozlamalarni panel orqali o'zgartirish**
(bo'lim qo'shish, soatlarni tahrirlash, qoidalar darhol kuchga kirishi),
50 ta bir vaqtdagi bron urinishi, fayl buzilgandan keyin tiklanish, zaxira sozlamalari.

---

## Sozlash

Kundalik sozlamalar (bo'limlar, ish soatlari, navbat qoidalari, manzil) —
**admin panelidagi ⚙️ Sozlamalar** orqali, kodga tegmasdan.

Kod darajasida qoladiganlar ([config.py](config.py)):

- `DEFAULT_DEPARTMENTS`, `DEFAULT_RULES`, `DEFAULT_CLINIC` — faqat **birinchi
  ishga tushish** uchun boshlang'ich qiymatlar
- `LIMITS` — panelda ruxsat etilgan chegaralar (masalan, oldindan yozilish 1–30 kun)
- `ADMIN_PAGE_SIZE`, `PASSWORD_MIN_LENGTH`, `LOGIN_MAX_ATTEMPTS`, `LOGIN_BLOCK_MINUTES`

---

## Ma'lum cheklovlar

- **Bitta jarayon** — JSON saqlash bir vaqtda bitta bot nusxasiga mo'ljallangan.
  Railway'da `numReplicas` 1 da qoldirilgan. Bir nechta nusxada (horizontal scaling)
  ishlatish uchun PostgreSQL kerak bo'ladi.
- **Zaxira interval bilan** — hard kill (SIGKILL) bo'lsa oxirgi bir necha daqiqa
  yo'qolishi mumkin. Shuning uchun Railway Volume asosiy himoya, GitHub esa qo'shimcha.
- Ko'p tillilik yo'q (faqat o'zbekcha).

Batafsil ro'yxat: [Task.md](Task.md)
