"""data.json ni GitHub'ga zaxiralash va u yerdan tiklash.

NIMA UCHUN KERAK
----------------
Railway (Heroku, Render, Fly.io ham) konteynerlarida disk **vaqtinchalik**:
har bir redeploy yoki yangi serverga ko'chirishda yozilgan fayllar yo'qoladi.
Ya'ni hech narsa qilinmasa, har deploy'dan keyin barcha bemorlar va
navbatlar o'chib ketadi.

MA'LUMOT QAYERDAN QAYTADI — BITTA QOIDA
---------------------------------------
Bot ishga tushganda lokal fayl va GitHub'dagi zaxira SOLISHTIRILADI va
**versiyasi (`revision`) katta bo'lgani yutadi**:

    lokal yo'q / bo'sh      -> GitHub'dan tiklanadi
    GitHub'da yo'q          -> lokal qoladi
    GitHub revision > lokal -> GitHub'dan tiklanadi (lokal nusxa .bak ga saqlanadi)
    aks holda               -> lokal qoladi

Shu tufayli "ma'lumot ikki joyda, qaysi biri to'g'ri?" degan noaniqlik yo'q —
har doim eng so'nggi holat tiklanadi.

XAVFSIZLIK
----------
Zaxira faylida bemorlarning ismi va telefon raqami bo'ladi. Ikki rejim bor:

  1. BACKUP_ENCRYPT_KEY berilgan -> fayl shifrlanadi (scrypt + Fernet/AES-128).
     Bunday holda PUBLIC repozitoriy ham xavfsiz: ichidagi ma'lumot o'qilmaydi.
  2. Kalit berilmagan -> fayl ochiq JSON. Bunda bot FAQAT private repozitoriyga
     yozadi, public bo'lsa zaxiralashni o'zi o'chiradi.

Zaxirani qo'lda ochish:
    python backup.py --decrypt backup.enc data.json
"""

import asyncio
import base64
import hashlib
import json
import logging
import secrets
import sys
from pathlib import Path

import aiohttp
from cryptography.fernet import Fernet, InvalidToken

from config import (
    BACKUP_BRANCH,
    BACKUP_ENCRYPT_KEY,
    BACKUP_FILE,
    BACKUP_INTERVAL_MINUTES,
    BACKUP_REPO,
    BACKUP_TOKEN,
    DATA_PATH,
)
from utils import now

log = logging.getLogger(__name__)

API = "https://api.github.com"
TIMEOUT = aiohttp.ClientTimeout(total=30)

MAGIC = b"NAVBAT1"  # shifrlangan faylni ochiq JSON'dan ajratish uchun
SALT_LEN = 16
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1


# --------------------------------------------------------------------------
# Shifrlash
# --------------------------------------------------------------------------

def _derive_key(passphrase: str, salt: bytes) -> bytes:
    raw = hashlib.scrypt(passphrase.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return base64.urlsafe_b64encode(raw)


def encrypt(plain: str, passphrase: str) -> bytes:
    """Har safar yangi salt bilan shifrlaydi."""
    salt = secrets.token_bytes(SALT_LEN)
    token = Fernet(_derive_key(passphrase, salt)).encrypt(plain.encode("utf-8"))
    return MAGIC + salt + token


def is_encrypted(blob: bytes) -> bool:
    return blob.startswith(MAGIC)


def decrypt(blob: bytes, passphrase: str) -> str | None:
    """Ochib bo'lmasa (kalit noto'g'ri yoki fayl buzilgan) None qaytaradi."""
    if not is_encrypted(blob):
        return None
    salt = blob[len(MAGIC):len(MAGIC) + SALT_LEN]
    token = blob[len(MAGIC) + SALT_LEN:]
    try:
        return Fernet(_derive_key(passphrase, salt)).decrypt(token).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


# --------------------------------------------------------------------------

class GitHubBackup:
    """GitHub Contents API orqali bitta faylni zaxiralaydi (git buyrug'i kerak emas)."""

    def __init__(
        self,
        repo: str = BACKUP_REPO,
        token: str = BACKUP_TOKEN,
        branch: str = BACKUP_BRANCH,
        remote_path: str = BACKUP_FILE,
        local_path: Path = DATA_PATH,
        interval_minutes: int = BACKUP_INTERVAL_MINUTES,
        encrypt_key: str = BACKUP_ENCRYPT_KEY,
    ) -> None:
        self.repo = repo
        self.token = token
        self.branch = branch
        self.remote_path = remote_path
        self.local_path = local_path
        self.interval = max(1, interval_minutes) * 60
        self.encrypt_key = encrypt_key

        self.enabled = bool(repo and token)
        self.last_hash: str | None = None
        self.last_success: str | None = None
        self.last_error: str | None = None
        self.last_restore: str | None = None
        self._sha: str | None = None
        self._task: asyncio.Task | None = None

    @property
    def encrypted(self) -> bool:
        return bool(self.encrypt_key)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Bot-navbat-backup",
        }

    @property
    def _url(self) -> str:
        return f"{API}/repos/{self.repo}/contents/{self.remote_path}"

    @staticmethod
    def _digest(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    def _fail(self, reason: str) -> None:
        self.enabled = False
        self.last_error = reason
        log.error("⛔ GitHub zaxirasi o'chirildi: %s", reason)

    # ------------------------------------------------------------------
    # Tekshiruv
    # ------------------------------------------------------------------

    async def verify(self) -> bool:
        """Token ishlaydimi, yozish huquqi bormi, public repo xavfsizmi."""
        if not self.enabled:
            log.info("GitHub zaxirasi sozlanmagan (BACKUP_REPO / BACKUP_TOKEN yo'q)")
            return False

        try:
            async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                async with session.get(f"{API}/repos/{self.repo}", headers=self._headers) as resp:
                    if resp.status == 404:
                        self._fail("repozitoriy topilmadi yoki token'da unga ruxsat yo'q")
                        return False
                    if resp.status == 401:
                        self._fail("BACKUP_TOKEN noto'g'ri yoki muddati tugagan")
                        return False
                    if resp.status != 200:
                        self._fail(f"GitHub javobi: HTTP {resp.status}")
                        return False
                    info = await resp.json()

            if not info.get("permissions", {}).get("push", True):
                self._fail("token'da yozish (push) huquqi yo'q")
                return False

            if not info.get("private"):
                if not self.encrypted:
                    self.enabled = False
                    self.last_error = "repo PUBLIC, shifrlash esa yoqilmagan"
                    log.error(
                        "⛔ ZAXIRALASH O'CHIRILDI: '%s' PUBLIC repozitoriy, "
                        "BACKUP_ENCRYPT_KEY esa berilmagan. Bemorlarning ismi va telefon "
                        "raqami ochiq internetga chiqib ketardi.\n"
                        "   Yechim: (a) BACKUP_ENCRYPT_KEY qo'ying — fayl shifrlanadi, yoki "
                        "(b) alohida PRIVATE repo ishlating.",
                        self.repo,
                    )
                    return False
                log.warning(
                    "⚠️ '%s' PUBLIC repozitoriy. Zaxira SHIFRLANGAN holda yuklanadi, "
                    "lekin baribir private repo xavfsizroq.", self.repo,
                )

            default_branch = info.get("default_branch", "main")
            if self.branch == default_branch:
                log.warning(
                    "⚠️ Zaxira '%s' shoxiga — bu repozitoriyning ASOSIY shoxi. "
                    "Agar shu repodan Railway deploy qilinayotgan bo'lsa, har zaxira "
                    "qayta deploy'ni ishga tushiradi va bot cheksiz qayta yuklanadi.\n"
                    "   Yechim: BACKUP_BRANCH=backup qo'ying.",
                    self.branch,
                )

            if not await self._ensure_branch(default_branch):
                return False

            log.info(
                "GitHub zaxirasi tayyor: %s (%s shoxi, har %d daqiqada, shifrlash: %s)",
                self.repo, self.branch, self.interval // 60, "yoqilgan" if self.encrypted else "yo'q",
            )
            return True

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            self._fail(f"GitHub'ga ulanib bo'lmadi: {e}")
            return False

    async def _ensure_branch(self, default_branch: str) -> bool:
        """Zaxira shoxi yo'q bo'lsa, uni asosiy shoxdan yaratadi.

        Shu tufayli foydalanuvchi GitHub'da qo'lda shox ochishi shart emas.
        """
        try:
            async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                async with session.get(
                    f"{API}/repos/{self.repo}/branches/{self.branch}", headers=self._headers
                ) as resp:
                    if resp.status == 200:
                        return True
                    if resp.status != 404:
                        self._fail(f"shoxni tekshirib bo'lmadi: HTTP {resp.status}")
                        return False

                # Asosiy shoxning oxirgi commit'ini olamiz
                async with session.get(
                    f"{API}/repos/{self.repo}/git/ref/heads/{default_branch}", headers=self._headers
                ) as resp:
                    if resp.status != 200:
                        self._fail(f"asosiy shox topilmadi: HTTP {resp.status}")
                        return False
                    sha = (await resp.json())["object"]["sha"]

                async with session.post(
                    f"{API}/repos/{self.repo}/git/refs",
                    headers=self._headers,
                    json={"ref": f"refs/heads/{self.branch}", "sha": sha},
                ) as resp:
                    if resp.status not in (200, 201):
                        text = await resp.text()
                        self._fail(f"'{self.branch}' shoxini yaratib bo'lmadi: HTTP {resp.status} {text[:120]}")
                        return False

            log.info("Zaxira uchun '%s' shoxi yaratildi", self.branch)
            return True

        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError) as e:
            self._fail(f"shox bilan ishlashda xato: {e}")
            return False

    # ------------------------------------------------------------------
    # Tiklash — "eng yangi nusxa yutadi"
    # ------------------------------------------------------------------

    def _local(self) -> dict | None:
        if not self.local_path.exists():
            return None
        try:
            return json.loads(self.local_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _local_has_data(self) -> bool:
        data = self._local()
        return bool(data and (data.get("users") or data.get("appointments")))

    @staticmethod
    def _revision(data: dict | None) -> int:
        return int((data or {}).get("revision", 0))

    async def sync_on_startup(self) -> str:
        """Lokal va zaxirani solishtiradi, kerak bo'lsa tiklaydi.

        Qaytaradi: 'restored' | 'local' | 'no-backup' | 'disabled'
        """
        if not self.enabled:
            return "disabled"

        remote_text = await self._download()
        if remote_text is None:
            log.info("GitHub'da zaxira topilmadi — lokal ma'lumot bilan davom etamiz")
            return "no-backup"

        try:
            remote = json.loads(remote_text)
        except json.JSONDecodeError:
            log.error("GitHub'dagi zaxira buzilgan yoki shifr kaliti noto'g'ri — tiklanmadi")
            self.last_error = "zaxira o'qilmadi (kalit noto'g'rimi?)"
            return "local"

        local = self._local()
        local_rev, remote_rev = self._revision(local), self._revision(remote)
        has_local = bool(local and (local.get("users") or local.get("appointments")))

        if has_local and local_rev >= remote_rev:
            log.info(
                "Lokal ma'lumot yangiroq yoki teng (lokal r%d >= zaxira r%d) — tiklash kerak emas",
                local_rev, remote_rev,
            )
            self.last_hash = self._digest(self.local_path.read_bytes())
            return "local"

        # Tiklaymiz. Lokal nusxa yo'qolib ketmasligi uchun avval chetga olamiz.
        if has_local:
            safety = self.local_path.with_suffix(self.local_path.suffix + ".before-restore.bak")
            safety.write_text(self.local_path.read_text(encoding="utf-8"), encoding="utf-8")
            log.warning(
                "Zaxira yangiroq (zaxira r%d > lokal r%d). Lokal nusxa saqlandi: %s",
                remote_rev, local_rev, safety.name,
            )

        self.local_path.parent.mkdir(parents=True, exist_ok=True)
        self.local_path.write_text(remote_text, encoding="utf-8")
        self.last_hash = self._digest(remote_text.encode("utf-8"))
        self.last_restore = now().strftime("%d.%m.%Y %H:%M")

        log.warning(
            "♻️ Ma'lumot GitHub zaxirasidan tiklandi: %d bemor, %d navbat, %d admin (r%d, %s)",
            len(remote.get("users", {})), len(remote.get("appointments", [])),
            len(remote.get("admins", {})), remote_rev, remote.get("saved_at", "—"),
        )
        return "restored"

    async def _download(self) -> str | None:
        """Zaxirani yuklab oladi va kerak bo'lsa deshifrlaydi."""
        try:
            async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                async with session.get(
                    self._url, headers=self._headers, params={"ref": self.branch}
                ) as resp:
                    if resp.status == 404:
                        return None
                    if resp.status != 200:
                        log.error("Zaxirani yuklab bo'lmadi: HTTP %s", resp.status)
                        return None
                    info = await resp.json()

            self._sha = info.get("sha")
            blob = base64.b64decode(info["content"])

            if is_encrypted(blob):
                if not self.encrypt_key:
                    log.error("Zaxira shifrlangan, lekin BACKUP_ENCRYPT_KEY berilmagan")
                    self.last_error = "zaxira shifrlangan, kalit yo'q"
                    return None
                text = decrypt(blob, self.encrypt_key)
                if text is None:
                    log.error("Zaxirani ochib bo'lmadi — BACKUP_ENCRYPT_KEY noto'g'ri")
                    self.last_error = "shifr kaliti noto'g'ri"
                return text

            return blob.decode("utf-8")

        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, ValueError) as e:
            log.error("Zaxirani yuklashda xato: %s", e)
            return None

    # ------------------------------------------------------------------
    # Yuklash
    # ------------------------------------------------------------------

    async def upload(self, force: bool = False) -> bool:
        """data.json ni GitHub'ga yuklaydi (o'zgarmagan bo'lsa yubormaydi)."""
        if not self.enabled or not self.local_path.exists():
            return False

        plain = self.local_path.read_bytes()
        digest = self._digest(plain)
        if not force and digest == self.last_hash:
            return False

        payload = encrypt(plain.decode("utf-8"), self.encrypt_key) if self.encrypted else plain

        if self._sha is None:
            await self._fetch_sha()

        body = {
            "message": f"Zaxira: {now().strftime('%Y-%m-%d %H:%M')} (avtomatik)",
            "content": base64.b64encode(payload).decode("ascii"),
            "branch": self.branch,
        }
        if self._sha:
            body["sha"] = self._sha

        try:
            async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                async with session.put(self._url, headers=self._headers, json=body) as resp:
                    if resp.status == 409:
                        log.info("Zaxira to'qnashuvi — sha yangilanmoqda, keyingi urinishda yuboriladi")
                        self._sha = None
                        await self._fetch_sha()
                        return False
                    if resp.status not in (200, 201):
                        text = await resp.text()
                        self.last_error = f"HTTP {resp.status}"
                        log.error("Zaxira yuklanmadi: HTTP %s — %s", resp.status, text[:200])
                        return False
                    result = await resp.json()

            self._sha = result.get("content", {}).get("sha")
            self.last_hash = digest
            self.last_success = now().strftime("%d.%m.%Y %H:%M")
            self.last_error = None
            log.info("💾 Zaxira GitHub'ga yuklandi (%s)", self.last_success)
            return True

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            self.last_error = str(e)
            log.error("Zaxira yuklashda xato: %s", e)
            return False

    async def _fetch_sha(self) -> None:
        try:
            async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                async with session.get(
                    self._url, headers=self._headers, params={"ref": self.branch}
                ) as resp:
                    if resp.status == 200:
                        self._sha = (await resp.json()).get("sha")
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass  # fayl hali yo'q — yangi yaratiladi

    # ------------------------------------------------------------------
    # Fonda ishlash
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.interval)
                await self.upload()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Zaxiralash siklida kutilmagan xato")

    def start(self) -> None:
        if self.enabled and self._task is None:
            self._task = asyncio.create_task(self._loop(), name="github-backup")

    async def stop(self) -> None:
        """To'xtashdan oldin oxirgi holatni majburan yuklaydi."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self.enabled:
            await self.upload(force=True)

    # ------------------------------------------------------------------

    def status_line(self) -> str:
        """Admin panelida ko'rsatish uchun qisqa holat."""
        if not self.enabled:
            return f"💾 Zaxira: <b>o'chiq</b>{f' ({self.last_error})' if self.last_error else ''}"

        lock = "🔒" if self.encrypted else "🔓"
        if self.last_error:
            return f"💾 Zaxira {lock}: ⚠️ <b>xato</b> — {self.last_error}"
        if self.last_success:
            return f"💾 Zaxira {lock}: ✅ {self.last_success}"
        return f"💾 Zaxira {lock}: yoqilgan, hali yuborilmagan"


# Butun ilova uchun bitta nusxa
backup = GitHubBackup()


# --------------------------------------------------------------------------
# Qo'lda deshifrlash: python backup.py --decrypt <shifrlangan> <natija.json>
# --------------------------------------------------------------------------

def _cli() -> None:
    if len(sys.argv) < 2 or sys.argv[1] != "--decrypt":
        print("Ishlatish:\n"
              "  python backup.py --decrypt <shifrlangan_fayl> [natija.json]\n\n"
              "Kalit BACKUP_ENCRYPT_KEY o'zgaruvchisidan olinadi (.env dan ham o'qiladi).")
        raise SystemExit(1)

    if not BACKUP_ENCRYPT_KEY:
        raise SystemExit("❌ BACKUP_ENCRYPT_KEY topilmadi (.env yoki muhit o'zgaruvchisi).")

    src = Path(sys.argv[2])
    dst = Path(sys.argv[3]) if len(sys.argv) > 3 else src.with_suffix(".decrypted.json")

    blob = src.read_bytes()
    if not is_encrypted(blob):
        raise SystemExit("ℹ️ Bu fayl shifrlanmagan — uni shundoq ochsa bo'ladi.")

    text = decrypt(blob, BACKUP_ENCRYPT_KEY)
    if text is None:
        raise SystemExit("❌ Ochib bo'lmadi — BACKUP_ENCRYPT_KEY noto'g'ri yoki fayl buzilgan.")

    dst.write_text(text, encoding="utf-8")
    data = json.loads(text)
    print(f"✅ Ochildi: {dst}")
    print(f"   {len(data.get('users', {}))} bemor, {len(data.get('appointments', []))} navbat, "
          f"r{data.get('revision', 0)} ({data.get('saved_at', '—')})")


if __name__ == "__main__":
    _cli()
