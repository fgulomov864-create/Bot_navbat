# Bot_navbat — kamchiliklar tahlili va bajarilgan ishlar

Bu hujjat loyihaning dastlabki holatida (bitta 507 qatorli `main.py`) topilgan
kamchiliklar ro'yxati va ularning hozirgi holati.

**Holat belgilari:** ✅ tuzatildi · 🔜 rejada · ⚪ ataylab qilinmadi

---

## 🔴 1-daraja: Xavfsizlik va maxfiylik

### ✅ 1.1. Bemorlar bazasi GitHub'ga yuklab yuborilgan
`dental_bot.db` commit qilingan edi va ichida haqiqiy bemor ismi va telefon raqami bor edi.

**Bajarildi:**
- `.gitignore` yaratildi: `*.db`, `data.json`, `.env`, `.venv/`, `.idea/`, `__pycache__/`, `*.log`.
- `git rm --cached dental_bot.db` — fayl kuzatuvdan chiqarildi (lokal nusxa joyida qoldi).

> ⚠️ **Hali qilinishi kerak:** fayl **eski commitlarda** saqlanib qolgan.
> To'liq o'chirish uchun git tarixini qayta yozish kerak:
> ```bash
> pip install git-filter-repo
> git filter-repo --invert-paths --path dental_bot.db --force
> git push --force origin main
> ```
> Yoki repozitoriyni **private** qilib qo'yish. Bu amal tarixni o'zgartirgani uchun
> qaror sizniki — men bajarmadim.

### ✅ 1.2. `.env` commit'ga tayyorlab qo'yilgan edi
`git status` da `A` (added) holatida turgan edi. Ichiga `BOT_TOKEN` yozilib commit
qilinsa, bot tokeni ochiq internetga chiqardi.

**Bajarildi:** `git rm --cached .env`; `.gitignore` ga qo'shildi; `.env.example` yaratildi.

### ✅ 1.3. `.idea/` (IDE sozlamalari) commit'ga qo'shilgan edi
**Bajarildi:** kuzatuvdan chiqarildi va `.gitignore` ga qo'shildi.

### ✅ 1.4. Admin ID kodning ichida ochiq yozilgan edi
Eski kod: `int(os.getenv("ADMIN_ID", 637554472))` — haqiqiy Telegram ID default qiymat edi.

**Bajarildi:** default olib tashlandi. `ADMIN_ID` endi ixtiyoriy va faqat `.env` dan o'qiladi
([config.py](config.py)). Ko'rsatilmasa — parolni birinchi kiritgan odam super admin bo'ladi.

### ✅ 1.5. `BOT_TOKEN` yo'qligi tekshirilmagan edi
**Bajarildi:** [config.py](config.py) dagi `_require()` tushunarli xabar bilan to'xtatadi:
`❌ .env faylida 'BOT_TOKEN' topilmadi.`

### ✅ 1.6. Navbatni bekor qilishda egalik tekshiruvi yo'q edi (IDOR)
Eski kod `del_{id}` ni olib, **kimligini tekshirmasdan** o'chirardi — `del_1`, `del_2` …
yuborib boshqa bemorlarning navbatini o'chirish mumkin edi.

**Bajarildi:** ikki qatlamli himoya —
1. `storage.cancel_booking(id, user_id=...)` egasi mos kelmasa `False` qaytaradi;
2. handler `callback.from_user.id` ni majburiy uzatadi ([handlers/booking.py](handlers/booking.py)).

Test bilan qoplandi: `tests_e2e.py::test_cancel_ownership`.

### ✅ 1.7. Ro'yxatdan o'tmagan foydalanuvchi ham navbat olardi
Oqibati: adminlar yangi navbat haqida xabar olmasdi (`JOIN users` bo'sh qaytardi).

**Bajarildi:** `_require_registration()` tekshiruvi qo'shildi; `JOIN` o'rniga
`LEFT JOIN` mantiqi (`_with_user`) — bemor ma'lumoti bo'lmasa ham xabar ketaveradi.

---

## 🟠 2-daraja: Ishlashdagi xatolar

### ✅ 2.1. Markdown parse xatosi ismdagi belgilardan
Bemor ismida `_`, `*`, `[` bo'lsa, `parse_mode="Markdown"` bilan yuborilgan xabarni
Telegram rad etardi.

**Bajarildi:** butun loyiha `ParseMode.HTML` ga o'tkazildi (`DefaultBotProperties` orqali
bir joyda), barcha foydalanuvchi matnlari `utils.esc()` bilan tozalanadi.

### ✅ 2.2. Vaqt zonasi hisobga olinmagan
`datetime.now()` server vaqtini olardi — xorijiy serverda (UTC) sana 5 soatga siljirdi.

**Bajarildi:** `utils.now()` → `datetime.now(ZoneInfo("Asia/Tashkent"))`.
`requirements.txt` ga **`tzdata`** qo'shildi — busiz Windows'da
`ZoneInfoNotFoundError` chiqishi tekshirib ko'rildi.

### ✅ 2.3. Bugunga navbat olish imkoni yo'q edi
Eski kod `range(1, 8)` — ertadan boshlanardi.

**Bajarildi:** bugundan boshlanadi; o'tib ketgan soatlar ⌛ bilan bloklanadi
(`MIN_LEAD_MINUTES = 30`); bugun bo'sh soat qolmasa, kun umuman ko'rsatilmaydi.

### ✅ 2.4. Band soatlar bo'limlar bo'yicha ajratilmagan edi
**Bajarildi:** bandlik `(bo'lim, kun, soat)` uchligi bo'yicha aniqlanadi.
Endi bir bo'limdagi bron ikkinchi bo'limdagi soatni bloklamaydi.

### ✅ 2.5. `UNIQUE` cheklovi migratsiya qilinmasdi
`ALTER TABLE` bilan `UNIQUE` qo'shib bo'lmaydi, shuning uchun eski bazada
`IntegrityError` hech qachon ishlamasdi.

**Bajarildi:** SQLite butunlay JSON'ga almashtirildi; bandlik xotiradagi
`_by_slot` indeksi bilan kafolatlanadi (`storage.py`).

### ✅ 2.6. Bir vaqtda ikki bemor (race condition)
**Bajarildi:** tekshirish va yozish bitta `asyncio.Lock` ichida bajariladi.
Test: **50 ta bir vaqtdagi urinishdan aynan 1 tasi o'tadi**
(`tests.py::test_race_condition`).

### ✅ 2.7. Admin bo'lmagan foydalanuvchida tugma osilib qolardi
`return` qilinardi, lekin `callback.answer()` chaqirilmasdi.

**Bajarildi:** `_guard()` har doim `answer(..., show_alert=True)` bilan javob beradi.

### ✅ 2.8. Xatoni ushlash bor edi, lekin log yo'q edi
**Bajarildi:** `services.send_safe()` — `TelegramForbiddenError` (bot bloklangan) va
`TelegramRetryAfter` (limit) alohida ushlanadi, qolganlari `log.exception` bilan yoziladi.

### ✅ 2.9. `int()` xatosi ushlanmagan edi
**Bajarildi:** qo'lda `split("_")` o'rniga aiogram'ning `CallbackData` fabrikalari
([callbacks.py](callbacks.py)). Buzuq callback `fallback.py` ga tushadi.

> Qo'shimcha topilma: soat `09:00` ichidagi `:` standart ajratuvchi bilan to'qnashardi —
> shuning uchun `sep="|"` tanlandi. Test bilan qoplandi.

### ✅ 2.10. Global error handler yo'q edi
**Bajarildi:** [handlers/errors.py](handlers/errors.py) — Dispatcher darajasida,
barcha routerlarni qoplaydi; foydalanuvchiga xabar beradi; "message is not modified"
kabi zararsiz xatolarni filtrlaydi.

### ✅ 2.11. Notanish matnga javob yo'q edi
**Bajarildi:** [handlers/fallback.py](handlers/fallback.py) — eng oxirgi router.
Eskirgan inline tugmalarga ham javob beradi.

### ✅ 2.12. *(yangi topilgan)* Windows konsolida emoji log botni yiqitardi
Windows konsoli `cp1252` ishlatadi → `UnicodeEncodeError`.
**Bajarildi:** `main.setup_logging()` chiqishni majburan UTF-8 ga o'tkazadi.

### ✅ 2.13. *(yangi topilgan)* Telefon kutilayotganda menyu tugmasi qamab qo'yardi
Foydalanuvchi telefon so'ralayotganda «📅 Navbat olish» bossa, bot uni raqam deb
o'qib «noto'g'ri raqam» derdi.
**Bajarildi:** `kb.MENU_BUTTONS` holat handlerlaridan chiqarib tashlandi
(telefon va parol kiritishda ham).

---

## 🟡 3-daraja: Arxitektura

### ✅ 3.1. Sinxron SQLite event loop'ni bloklardi
**Bajarildi:** o'qishlar xotiradan (disk yo'q), fayl yozish `asyncio.to_thread` da.
Parol hash'i (~0.1 s) ham alohida oqimda hisoblanadi.

### ✅ 3.2. Har handlerda ulanish qo'lda ochilib yopilardi (8 joyda, `try/finally` siz)
**Bajarildi:** butun ma'lumot mantiqi [storage.py](storage.py) ga ko'chirildi.
Handlerlarda birorta ham SQL/fayl amali yo'q.

### ✅ 3.3. Butun loyiha bitta faylda edi (507 qator)
**Bajarildi:** `config` / `storage` / `keyboards` / `callbacks` / `services` / `utils`
va 5 ta router ([handlers/](handlers/)).

### ✅ 3.4. FSM ishlatilmagan, callback'lar qo'lda parse qilinardi
**Bajarildi:** `CallbackData` fabrikalari + `StatesGroup` (ro'yxatdan o'tish, parol
kiritish, parolni o'zgartirish). Eski versiya uchun qoldirilgan `if len(parts) >= 3`
fallback'lari olib tashlandi.

### ✅ 3.5. `DB_NAME` dagi vaqtinchalik "hack"
`"dental_bot (2).db" if os.path.exists(...)` — olib tashlandi.
Yo'l endi **absolyut** (`BASE_DIR / ...`), bot boshqa papkadan ishga tushirilsa ham
o'sha bazani topadi.

### ✅ 3.6. `status` ustuni ishlatilmasdi (o'lik kod)
Bekor qilishda qator butunlay `DELETE` qilinardi — tarix yo'qolardi.

**Bajarildi:** `DELETE` o'rniga status `cancelled` ga o'zgaradi; `done` / `missed`
holatlari qo'shildi; `created_at` va `cancelled_at` yoziladi.

### ✅ 3.7. Takrorlanuvchi `parse_mode`
**Bajarildi:** `DefaultBotProperties(parse_mode=ParseMode.HTML)` — bir joyda.

### ✅ 3.8. Keraksiz import (`BotCommand`)
**Bajarildi:** `ruff check --select F,E9` toza o'tadi.

### ✅ 3.9. Logging kech sozlangan edi
**Bajarildi:** `setup_logging()` `main()` ning birinchi qatorida; konsol + aylanuvchi
fayl (`bot.log`, 5 MB × 3).

---

## 🟢 4-daraja: Funksiyalar

### ✅ 4.2. Admin panel (to'liq qayta yozildi)
Eski panelda faqat ro'yxat va "chaqirish" tugmasi bor edi.

**Endi `/admin` — parol bilan himoyalangan panel:**
- 🔐 Parol orqali kirish (boshlang'ich: `1234567890`)
- 👑 **Parolni to'g'ri kiritgan birinchi odam — super admin**
- 📋 Navbatlar — sahifalangan; 🚨 chaqirish · ✅ keldi · 🚫 kelmadi · ❌ bekor qilish
- 📊 Statistika — bemorlar, bugungi/kutilayotgan navbatlar, haftalik hisobot
- 👥 **Adminlar ro'yxati** — ism, username, ID, daraja, qo'shilgan sana
- ❌ **Adminni ro'yxatdan chiqarish** (faqat super admin, tasdiqlash bilan)
- 🔑 **Parolni o'zgartirish** (faqat super admin)
- 🚪 Adminlikdan chiqish

**Xavfsizlik:** parol `PBKDF2-SHA256` (200 000 iteratsiya, tasodifiy salt) bilan
saqlanadi; parol xabari chatdan darhol o'chiriladi; 5 xato urinishdan keyin 15 daqiqa
blok; super adminni hech kim (o'zi ham) chiqara olmaydi.

### ✅ 4.3. Admin panel har navbat uchun alohida xabar yuborardi
20-30 navbatda chat to'lardi va Telegram rate limit'ga urilardi.
**Bajarildi:** sahifalash (`ADMIN_PAGE_SIZE = 5`) + `send_safe` da 0.05 s oraliq.

### ✅ 4.4. Telefon raqamni qo'lda kiritish imkoni yo'q edi
**Bajarildi:** qo'lda kiritish + normallashtirish (`+998…`, `998…`, `90…`, tire/probel bilan);
**boshqa odamning kontaktini** yuborish bloklandi.

### ✅ 4.5. Kichik yetishmovchiliklar
- `/help` va `/cancel` komandalari qo'shildi
- Bemorni chaqirish xabarida endi bo'lim/kun/soat ko'rsatiladi (ilgari `time_slot`
  o'qilardi, lekin ishlatilmasdi)
- `MAX_ACTIVE_BOOKINGS = 3` limiti
- `storage.purge_old()` — eski yopilgan yozuvlarni tozalash

### 🔜 4.1. Avtomatik eslatma
Bemorga «ogohlantirish yuboriladi» deb va'da qilinadi, lekin bu hali ham **admin
qo'lda tugma bosganda** ishlaydi. Rejada: `apscheduler` bilan qabuldan 1 kun va
1 soat oldin avtomatik eslatma.

### ⚪ Ataylab qilinmadi
- Ko'p tillilik (rus tili) — hozircha talab qilinmadi
- Shifokor tanlash — bo'limlar darajasi yetarli deb topildi
- Ish soatlarini bot orqali o'zgartirish — `config.py` dan tahrirlanadi

---

## 🔵 5-daraja: Infratuzilma

| Holat | Element | Izoh |
|---|---|---|
| ✅ | `README.md` | O'rnatish, sozlash, admin panel, loyiha tuzilishi |
| ✅ | `.gitignore` | Maxfiy fayllar va shaxsiy ma'lumotlar bloklangan |
| ✅ | `.env.example` | Barcha sozlamalar izohi bilan |
| ✅ | **Testlar** | `tests.py` (134 ta) + `tests_e2e.py` (97 ta) = **231 ta test** |
| ✅ | `requirements.txt` | Faqat to'g'ridan-to'g'ri bog'liqliklar (19 → 3 ta) + `tzdata` |
| ✅ | Lint | `ruff check --select F,E9` toza |
| 🔜 | `Dockerfile` | Deploy hozircha qo'lda |
| 🔜 | CI (GitHub Actions) | Testlarni avtomatik ishga tushirish |

---

## 📦 SQLite → JSON o'tkazish

Loyiha SQLite'dan JSON saqlashga o'tkazildi.

**Bajarildi:**
- [storage.py](storage.py) — JSON qatlami: xotirada 3 ta indeks
  (`id → navbat`, `user_id → navbatlar`, `(bo'lim, kun, soat) → navbat`),
  `asyncio.Lock` bilan seriyalash, **atomar yozish** (`.tmp` + `os.replace` + `fsync`),
  har saqlashda `.bak` zaxira, buzilgan fayldan **avtomatik tiklanish**.
- [migrate_to_json.py](migrate_to_json.py) — konvertor. Uchala eski sxemani tushunadi
  (`service_type` siz / bilan / yangi), eski `.db` faylga tegmaydi.
- `aiosqlite` bog'liqligi olib tashlandi (konvertor standart `sqlite3` dan foydalanadi).

**Haqiqiy baza ko'chirildi:** 1 bemor + 1 navbat → `data.json` (590 bayt), tekshirildi.

> ⚠️ **Diqqat:** JSON saqlash **bitta bot nusxasiga** mo'ljallangan. Bir nechta
> jarayonda (horizontal scaling) ishlatilsa, fayl ustida to'qnashuv bo'ladi —
> u holda PostgreSQL kerak bo'ladi. Hozirgi hajm uchun JSON mutlaqo yetarli.

---

## ✅ Tekshirish natijalari

```
python tests.py       →  ✅ o'tdi: 134   ❌ yiqildi: 0
python tests_e2e.py   →  ✅ o'tdi:  97   ❌ yiqildi: 0
ruff check            →  All checks passed!
Telegram ulanishi     →  OK  (@uzb123_kon_bot)
```

Testlar quyidagilarni qoplaydi: telefon validatsiyasi, vaqt zonasi, HTML escaping,
callback round-trip (64 bayt limiti), parol hash, adminlar iyerarxiyasi, bandlik,
**egalik tekshiruvi**, 50 ta bir vaqtdagi bron urinishi, diskka saqlash/tiklash,
buzilgan fayldan tiklanish, brute-force bloki, SQLite→JSON migratsiyasi.

---

## 📌 Sizga qolgan ishlar

1. **Git tarixini tozalash** — `dental_bot.db` eski commitlarda qolgan (1.1 ga qarang).
   Yoki repozitoriyni private qiling.
2. **Admin parolini almashtiring** — panelga birinchi kirganingizda `1234567890` ni
   o'zgartiring (🔑 tugmasi).
3. **`.env` ni to'ldiring** — `BOT_TOKEN` majburiy; `ADMIN_ID` ni ko'rsatsangiz,
   parolsiz ham super admin bo'lasiz.
4. Bot ishlayotganiga ishonch hosil qilgach, `dental_bot.db` ni qo'lda o'chiring.
