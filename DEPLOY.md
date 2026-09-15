# 🚂 Railway'ga joylash — qadamma-qadam

Har qadamdan keyin `python check.py` ni ishlatib, nima tayyor ekanini ko'rib turing.

---

## 0-qadam. Tekshirib oling

```bash
python check.py
```

Ekranda nima yetishmayotgani ro'yxat bo'lib chiqadi. Oxirida
`✅ Hammasi joyida` yozuvi paydo bo'lguncha quyidagi qadamlarni bajaring.

---

## 1-qadam. Telegram token

1. Telegramda [@BotFather](https://t.me/BotFather) ga `/newbot` yozing
   (yoki mavjud bot uchun `/token`)
2. Olingan tokenni `.env` ga qo'ying:

```bash
BOT_TOKEN=7921640924:AAE...
```

---

## 2-qadam. O'z Telegram ID'ingiz

> ⚠️ Bu yerga **botning** emas, **o'zingizning** ID'ingiz kerak.
> Ular har xil: botning ID'si token boshidagi raqam bilan bir xil.

1. [@userinfobot](https://t.me/userinfobot) ga `/start` yozing
2. U bergan raqamni `.env` ga qo'ying:

```bash
ADMIN_ID=[123456789]
```

Bir nechta odam bo'lsa: `ADMIN_ID=[123456789, 987654321]`

Bo'sh qoldirsangiz ham bo'ladi — u holda `/admin` da parolni birinchi
to'g'ri kiritgan odam super admin bo'ladi.

---

## 3-qadam. GitHub token (zaxira uchun)

Zaxirasiz Railway'da har redeploy'da ma'lumot yo'qoladi.

1. [github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens)
   → **Generate new token** → *Fine-grained*
2. **Repository access** → *Only select repositories* → `Bot_navbat`
3. **Permissions** → *Repository permissions* → **Contents: Read and write**
4. Tokenni `.env` ga qo'ying:

```bash
BACKUP_TOKEN=github_pat_...
```

`.env` dagi qolgan zaxira sozlamalari allaqachon to'g'ri turibdi:

```bash
BACKUP_REPO=fgulomov864-create/Bot_navbat
BACKUP_BRANCH=backup          # main EMAS — pastdagi izohga qarang
BACKUP_ENCRYPT_KEY=<yaratilgan>
```

> **Nega `backup` shoxi?** Railway `main` ga har push'da qayta deploy qiladi.
> Zaxira ham `main` ga yozilsa: zaxira → deploy → bot qayta ishga tushadi →
> yana zaxira → cheksiz sikl. `backup` shoxi buni butunlay oldini oladi.
> Shox mavjud bo'lmasa, bot uni o'zi yaratadi.

> **Nega shifrlash?** `Bot_navbat` — public repozitoriy. Shifrlashsiz
> bemorlarning ismi va telefoni ochiq internetga chiqardi. Kalit bilan
> GitHub'da faqat o'qib bo'lmaydigan blob turadi.
> ⚠️ **Kalitni yo'qotmang** — nusxasini boshqa joyga ham saqlang.

---

## 4-qadam. Lokalda sinab ko'ring

```bash
python check.py      # ✅ Hammasi joyida bo'lishi kerak
python main.py
```

Telegramda botga `/start` yozing, keyin `/admin` → parol `1234567890`.
Panel ochilsa — hammasi ishlayapti. `Ctrl+C` bilan to'xtating.

---

## 5-qadam. Railway

### 5.1. Loyihani ulash
[railway.com](https://railway.com) → **New Project** →
**Deploy from GitHub repo** → `Bot_navbat`

`Dockerfile` va `railway.json` tayyor — Railway ularni o'zi topadi.

### 5.2. Volume (ma'lumot yo'qolmasligining asosiy kafolati)
**Settings** → **Volumes** → **Add Volume** → Mount path: `/data`

### 5.3. Variables
**Variables** bo'limiga `.env` dagilarni ko'chiring, lekin `DATA_FILE` ni
o'zgartiring:

```bash
BOT_TOKEN=<tokeningiz>
ADMIN_ID=[<sizning ID>]
ADMIN_PASSWORD=<kuchli parol>
TIMEZONE=Asia/Tashkent

DATA_FILE=/data/data.json          ← MUHIM: Volume yo'li

BACKUP_REPO=fgulomov864-create/Bot_navbat
BACKUP_TOKEN=<github tokeni>
BACKUP_BRANCH=backup
BACKUP_ENCRYPT_KEY=<kalit>
BACKUP_INTERVAL_MINUTES=5
```

### 5.4. Deploy
Railway o'zi qurib ishga tushiradi. **Deployments → Logs** da quyidagilar
chiqishi kerak:

```
Ma'lumotlar fayli: /data/data.json
GitHub zaxirasi tayyor: fgulomov864-create/Bot_navbat (backup shoxi, ...)
Baza yuklandi: data.json (...)
🔔 Eslatma xizmati ishga tushdi
Bot ishga tushdi: @uzb123_kon_bot
```

---

## 6-qadam. Birinchi sozlash

1. Telegramda `/admin` → parol → siz **super admin** bo'lasiz
2. **🔑 Parolni o'zgartirish** — standart parolni darhol almashtiring
3. **⚙️ Sozlamalar** → bo'limlar, ish soatlari, manzil, eslatmalarni sozlang
4. **💾 Hozir zaxiralash** — zaxira ishlayotganini tekshiring
   (GitHub'da `backup` shoxida `backup/data.json` paydo bo'lishi kerak)

---

## Ma'lumot yo'qolmasligi qanday kafolatlanadi

| Qatlam | Nima qiladi |
|---|---|
| **Railway Volume** | Redeploy, restart, crash — `/data` saqlanib qoladi |
| **GitHub zaxirasi** | Har 5 daqiqada (o'zgargan bo'lsa) va to'xtashdan oldin yuklanadi |
| **Ishga tushishda tiklash** | Lokal va zaxira solishtiriladi, **`revision` raqami kattarog'i yutadi** |
| **Atomar yozish** | `.tmp` + `os.replace` + `fsync` — yozish uzilsa ham fayl butun |
| **`.bak` nusxa** | Fayl buzilsa, undan avtomatik tiklanadi |

Yangi serverga butunlay noldan qo'ysangiz ham: bot ishga tushadi → GitHub'dagi
zaxirani topadi → lokal bo'sh bo'lgani uchun undan tiklaydi → hamma bemor,
navbat, admin va sozlamalar qaytadi.

---

## Zaxirani qo'lda ochish

```bash
python backup.py --decrypt backup.enc data.json
```

Kalit `.env` dagi `BACKUP_ENCRYPT_KEY` dan olinadi.

---

## Muammo bo'lsa

| Belgi | Sabab va yechim |
|---|---|
| `❌ .env faylida 'BOT_TOKEN' topilmadi` | Railway Variables'ga `BOT_TOKEN` qo'shilmagan |
| `ZoneInfoNotFoundError` | `tzdata` o'rnatilmagan — `requirements.txt` to'liq ekanini tekshiring |
| `ZAXIRALASH O'CHIRILDI: ... PUBLIC` | `BACKUP_ENCRYPT_KEY` qo'shilmagan |
| Bot har necha daqiqada qayta ishga tushadi | `BACKUP_BRANCH=main` qo'yilgan — `backup` qiling |
| Redeploy'dan keyin ma'lumot yo'q | Volume ulanmagan yoki `DATA_FILE=/data/data.json` yozilmagan |
| Panel ochilmayapti | `ADMIN_ID` ga botning ID'si yozilgan bo'lishi mumkin — `python check.py` aytadi |

---

## Hali hal qilinmagan narsa

Eski `dental_bot.db` (bemor ismi va telefoni bilan) **git tarixida** qolgan —
repo public bo'lgani uchun u hozir ham ko'rinadi. Tarixni tozalash:

```bash
pip install git-filter-repo
git filter-repo --invert-paths --path dental_bot.db --force
git push --force origin main
```

Yoki repozitoriyni **private** qiling. Bu amal tarixni qaytarib bo'lmaydigan
tarzda o'zgartirgani uchun qaror sizniki.
