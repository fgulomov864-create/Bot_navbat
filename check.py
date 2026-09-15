"""Deploy oldidan tekshiruv — nima tayyor, nima yetishmayapti.

Ishlatish:
    python check.py

Hech narsani o'zgartirmaydi, faqat tekshiradi.
Railway'da ham ishlaydi: `python check.py` deb konsoldan chaqirsangiz,
o'sha yerdagi muhit sozlamalari tekshiriladi.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OK, WARN, FAIL = "✅", "⚠️ ", "❌"
problems: list[str] = []
warnings: list[str] = []


def line(status: str, text: str, hint: str = "") -> None:
    print(f"  {status} {text}")
    if hint:
        print(f"        → {hint}")
    if status == FAIL:
        problems.append(text)
    elif status == WARN:
        warnings.append(text)


def section(title: str) -> None:
    print(f"\n{title}")


# --------------------------------------------------------------------------

def check_python() -> None:
    section("🐍 Python")
    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 11):
        line(OK, f"Python {major}.{minor}")
    else:
        line(FAIL, f"Python {major}.{minor} — 3.11 yoki yangiroq kerak")


def check_packages() -> None:
    section("📦 Kutubxonalar")
    for module, package in [
        ("aiogram", "aiogram"),
        ("aiohttp", "aiohttp"),
        ("dotenv", "python-dotenv"),
        ("cryptography", "cryptography"),
    ]:
        try:
            __import__(module)
            line(OK, package)
        except ImportError:
            line(FAIL, f"{package} o'rnatilmagan", "pip install -r requirements.txt")

    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(os.getenv("TIMEZONE", "Asia/Tashkent"))
        line(OK, "vaqt zonasi bazasi (tzdata)")
    except Exception as e:
        line(FAIL, f"vaqt zonasi topilmadi: {e}", "pip install tzdata")


def check_env() -> tuple[bool, object]:
    section("🔑 Sozlamalar (.env / Railway Variables)")

    if not Path(".env").exists() and not os.getenv("BOT_TOKEN"):
        line(FAIL, ".env fayli ham, BOT_TOKEN o'zgaruvchisi ham yo'q",
             "cp .env.example .env  va ichini to'ldiring")
        return False, None

    try:
        import config
    except RuntimeError as e:
        line(FAIL, str(e).splitlines()[0])
        return False, None

    token = config.BOT_TOKEN
    if not token or token.startswith("BU_YERGA") or token == "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA":
        line(FAIL, "BOT_TOKEN to'ldirilmagan", "@BotFather dan olib .env ga qo'ying")
    else:
        line(OK, f"BOT_TOKEN ({token.split(':')[0]}:…)")

    if config.ADMIN_IDS:
        line(OK, f"ADMIN_ID: {config.ADMIN_IDS} — avtomatik super admin")
    else:
        line(OK, "ADMIN_ID bo'sh — parolni birinchi kiritgan odam super admin bo'ladi")

    if config.DEFAULT_ADMIN_PASSWORD == "1234567890":
        line(WARN, "Admin paroli hali standart (1234567890)",
             "Panelga kirgach ⚙️ 🔑 orqali almashtiring")
    else:
        line(OK, "Admin paroli o'zgartirilgan")

    line(OK, f"Vaqt zonasi: {config.TIMEZONE}")
    return True, config


def check_data(config) -> None:
    section("💾 Ma'lumotlar fayli")
    path = config.DATA_PATH
    print(f"        yo'l: {path}")

    if str(path).startswith(("/data", "C:\\data")) or "/data/" in str(path).replace("\\", "/"):
        line(OK, "Doimiy papkaga (Volume) yo'naltirilgan")
    else:
        line(WARN, "Loyiha papkasida saqlanmoqda",
             "Railway'da Volume ulab, DATA_FILE=/data/data.json qo'ying — "
             "aks holda har redeploy'da ma'lumot yo'qoladi")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        probe = path.parent / ".write-probe"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        line(OK, "Papkaga yozish mumkin")
    except OSError as e:
        line(FAIL, f"Papkaga yozib bo'lmadi: {e}")

    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            line(OK, f"Mavjud baza o'qildi: {len(data.get('users', {}))} bemor, "
                     f"{len(data.get('appointments', []))} navbat, "
                     f"{len(data.get('admins', {}))} admin (r{data.get('revision', 0)})")
        except json.JSONDecodeError:
            line(FAIL, "Mavjud data.json buzilgan", "data.json.bak dan tiklanadi")
    else:
        line(OK, "Baza hali yo'q — birinchi ishga tushishda yaratiladi")


async def check_telegram(config) -> None:
    section("🤖 Telegram")
    token = config.BOT_TOKEN
    if not token or token.startswith("BU_YERGA"):
        line(WARN, "Token yo'q — tekshirib bo'lmadi")
        return

    from aiogram import Bot
    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        line(OK, f"Ulandi: @{me.username} (id={me.id})")

        # Keng tarqalgan xato: ADMIN_ID ga botning o'z ID'si yoziladi.
        # Bunda bot o'zini admin qilishga urinadi, siz esa panelga kira olmaysiz.
        if me.id in config.ADMIN_IDS:
            line(FAIL, f"ADMIN_ID da BOTNING O'ZINING id'si turibdi ({me.id})",
                 "U yerga O'ZINGIZNING Telegram ID'ingiz kerak — "
                 "@userinfobot ga /start yozib bilib oling")
    except Exception as e:
        line(FAIL, f"Ulanmadi: {type(e).__name__}", str(e)[:100])
    finally:
        await bot.session.close()


async def check_backup(config) -> None:
    section("☁️ GitHub zaxirasi")

    if not config.BACKUP_REPO and not config.BACKUP_TOKEN:
        line(WARN, "Sozlanmagan — zaxira bo'lmaydi",
             "Railway'da ma'lumot yo'qolmasligi uchun sozlang yoki Volume ulang")
        return

    if not config.BACKUP_TOKEN:
        line(FAIL, "BACKUP_TOKEN to'ldirilmagan",
             "github.com/settings/personal-access-tokens → Contents: Read and write")
        return
    if not config.BACKUP_REPO:
        line(FAIL, "BACKUP_REPO to'ldirilmagan", "namuna: foydalanuvchi/repo")
        return

    line(OK, f"Repo: {config.BACKUP_REPO} ({config.BACKUP_BRANCH} shoxi)")

    if config.BACKUP_ENCRYPT_KEY:
        line(OK, f"Shifrlash yoqilgan ({len(config.BACKUP_ENCRYPT_KEY)} belgili kalit)")
    else:
        line(WARN, "Shifrlash o'chiq — repo private bo'lishi SHART")

    from backup import GitHubBackup
    probe = GitHubBackup()
    if await probe.verify():
        line(OK, "GitHub bilan aloqa va huquqlar joyida")
        if probe.branch == "main":
            line(WARN, "Zaxira 'main' shoxiga yozilmoqda",
                 "Railway shu repodan deploy qilsa, cheksiz redeploy sikli bo'ladi. "
                 "BACKUP_BRANCH=backup qiling")
    else:
        line(FAIL, f"Zaxira ishlamaydi: {probe.last_error or 'sabab nomaʼlum'}")


def check_git() -> None:
    section("🗂 Git")

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()

    tracked = git("ls-files").splitlines()
    leaked = [f for f in (".env", "data.json", "dental_bot.db", "bot.log") if f in tracked]
    if leaked:
        line(FAIL, f"Maxfiy fayl git'da: {', '.join(leaked)}", "git rm --cached <fayl>")
    else:
        line(OK, "Maxfiy fayllar git'da yo'q")

    if git("log", "--all", "--oneline", "--", "dental_bot.db"):
        line(WARN, "Eski bemor bazasi git TARIXIDA qolgan",
             "git filter-repo --invert-paths --path dental_bot.db --force "
             "(yoki repo'ni private qiling)")
    else:
        line(OK, "Git tarixi toza")

    status = git("status", "--porcelain")
    if status:
        line(WARN, f"Commit qilinmagan o'zgarishlar bor ({len(status.splitlines())} fayl)")
    else:
        line(OK, "Hamma narsa commit qilingan")


def check_deploy_files() -> None:
    section("🚂 Deploy fayllari")
    for name, why in [
        ("Dockerfile", "konteyner"),
        ("railway.json", "Railway sozlamalari"),
        (".dockerignore", "maxfiy fayllar image'ga tushmasligi"),
        ("requirements.txt", "bog'liqliklar"),
        (".github/workflows/tests.yml", "CI"),
    ]:
        if Path(name).exists():
            line(OK, f"{name} — {why}")
        else:
            line(FAIL, f"{name} yo'q")


# --------------------------------------------------------------------------

async def main() -> None:
    print("=" * 62)
    print("  Bot_navbat — deploy oldidan tekshiruv")
    print("=" * 62)

    check_python()
    check_packages()
    ok, config = check_env()

    if ok and config is not None:
        check_data(config)
        await check_telegram(config)
        await check_backup(config)

    check_git()
    check_deploy_files()

    print("\n" + "=" * 62)
    if problems:
        print(f"  ❌ Deploy'ga TAYYOR EMAS — {len(problems)} ta muammo:")
        for p in problems:
            print(f"     • {p}")
    elif warnings:
        print(f"  ✅ Deploy'ga tayyor. {len(warnings)} ta ogohlantirish bor:")
        for w in warnings:
            print(f"     • {w}")
    else:
        print("  ✅ Hammasi joyida — deploy qilsa bo'ladi.")
    print("=" * 62)

    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    asyncio.run(main())
