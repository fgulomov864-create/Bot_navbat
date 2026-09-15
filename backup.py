"""data.json ni GitHub'ga zaxiralash va u yerdan tiklash.

NIMA UCHUN KERAK
----------------
Railway (va Heroku, Render, Fly.io) konteynerlarida disk **vaqtinchalik**:
har bir redeploy yoki qayta ishga tushirishda yozilgan fayllar yo'qoladi.
Ya'ni hech narsa qilinmasa, har deploy'dan keyin barcha bemorlar va
navbatlar o'chib ketadi.

Bu modul ikki ish qiladi:
  1. **Tiklash** — bot ishga tushganda lokal baza bo'sh bo'lsa, oxirgi
     zaxirani GitHub'dan yuklab oladi;
  2. **Zaxiralash** — har N daqiqada (faqat ma'lumot O'ZGARGAN bo'lsa)
     faylni repozitoriyga yuklaydi.

git buyrug'i kerak emas — GitHub Contents API ishlatiladi.

⚠️ XAVFSIZLIK
-------------
Zaxira faylida bemorlarning ismi va telefon raqami bo'ladi.
Shuning uchun bot ishga tushishda repozitoriyning **private** ekanini tekshiradi
va public bo'lsa zaxiralashni butunlay o'chiradi.
"""

import asyncio
import base64
import hashlib
import json
import logging
from pathlib import Path

import aiohttp

from config import (
    BACKUP_BRANCH,
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


class GitHubBackup:
    """GitHub Contents API orqali bitta faylni zaxiralaydi."""

    def __init__(
        self,
        repo: str = BACKUP_REPO,
        token: str = BACKUP_TOKEN,
        branch: str = BACKUP_BRANCH,
        remote_path: str = BACKUP_FILE,
        local_path: Path = DATA_PATH,
        interval_minutes: int = BACKUP_INTERVAL_MINUTES,
    ) -> None:
        self.repo = repo
        self.token = token
        self.branch = branch
        self.remote_path = remote_path
        self.local_path = local_path
        self.interval = max(1, interval_minutes) * 60

        self.enabled = bool(repo and token)
        self.last_hash: str | None = None
        self.last_success: str | None = None
        self.last_error: str | None = None
        self._sha: str | None = None  # GitHub'dagi faylning joriy versiyasi
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Ichki yordamchilar
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Tekshiruv
    # ------------------------------------------------------------------

    async def verify(self) -> bool:
        """Token ishlaydimi va repozitoriy PRIVATE mi — shuni tekshiradi.

        Public repo topilsa, zaxiralash o'chiriladi: aks holda bemorlarning
        shaxsiy ma'lumotlari ochiq internetga chiqib ketardi.
        """
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

            if not info.get("private"):
                self.enabled = False
                self.last_error = "repozitoriy PUBLIC"
                log.error(
                    "⛔ ZAXIRALASH O'CHIRILDI: '%s' repozitoriysi PUBLIC. "
                    "Bemorlarning ismi va telefon raqami ochiq internetga chiqib ketardi. "
                    "Repo'ni private qiling yoki alohida private repo yarating.",
                    self.repo,
                )
                return False

            if not info.get("permissions", {}).get("push", True):
                self._fail("token'da yozish (push) huquqi yo'q")
                return False

            log.info("GitHub zaxirasi tayyor: %s (%s shoxi, har %d daqiqada)",
                     self.repo, self.branch, self.interval // 60)
            return True

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            self._fail(f"GitHub'ga ulanib bo'lmadi: {e}")
            return False

    def _fail(self, reason: str) -> None:
        self.enabled = False
        self.last_error = reason
        log.error("⛔ GitHub zaxirasi o'chirildi: %s", reason)

    # ------------------------------------------------------------------
    # Tiklash
    # ------------------------------------------------------------------

    async def restore_if_empty(self) -> bool:
        """Lokal baza yo'q yoki bo'sh bo'lsa, GitHub'dagi zaxiradan tiklaydi.

        Aynan shu narsa Railway'da redeploy'dan keyin ma'lumotni saqlab qoladi.
        Lokal bazada ma'lumot bo'lsa — TEGMAYDI (yangi ustiga eskisini yozmaslik uchun).
        """
        if not self.enabled:
            return False

        if self._local_has_data():
            log.info("Lokal bazada ma'lumot bor — zaxiradan tiklash kerak emas")
            return False

        content = await self._download()
        if content is None:
            log.info("GitHub'da zaxira topilmadi — toza bazadan boshlanadi")
            return False

        try:
            parsed = json.loads(content)
            users = len(parsed.get("users", {}))
            appts = len(parsed.get("appointments", []))
        except json.JSONDecodeError:
            log.error("GitHub'dagi zaxira buzilgan — tiklanmadi")
            return False

        self.local_path.parent.mkdir(parents=True, exist_ok=True)
        self.local_path.write_text(content, encoding="utf-8")
        self.last_hash = self._digest(content.encode("utf-8"))

        log.warning("♻️ Ma'lumot GitHub zaxirasidan tiklandi: %d bemor, %d navbat", users, appts)
        return True

    def _local_has_data(self) -> bool:
        if not self.local_path.exists():
            return False
        try:
            data = json.loads(self.local_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        return bool(data.get("users") or data.get("appointments"))

    async def _download(self) -> str | None:
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
            return base64.b64decode(info["content"]).decode("utf-8")

        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, ValueError) as e:
            log.error("Zaxirani yuklashda xato: %s", e)
            return None

    # ------------------------------------------------------------------
    # Yuklash
    # ------------------------------------------------------------------

    async def upload(self, force: bool = False) -> bool:
        """data.json ni GitHub'ga yuklaydi.

        Ma'lumot oxirgi zaxiradan beri o'zgarmagan bo'lsa — yubormaydi
        (keraksiz commit yaratmaslik uchun). force=True buni chetlab o'tadi.
        """
        if not self.enabled or not self.local_path.exists():
            return False

        payload = self.local_path.read_bytes()
        digest = self._digest(payload)

        if not force and digest == self.last_hash:
            return False  # o'zgarish yo'q

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
                        # Fayl GitHub'da o'zgargan — sha ni yangilab qayta urinamiz
                        log.info("Zaxira to'qnashuvi — sha yangilanmoqda")
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
        """GitHub'dagi faylning joriy versiyasini oladi (yangilash uchun shart)."""
        try:
            async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                async with session.get(
                    self._url, headers=self._headers, params={"ref": self.branch}
                ) as resp:
                    if resp.status == 200:
                        self._sha = (await resp.json()).get("sha")
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass  # fayl hali yo'q bo'lishi mumkin — yangi yaratiladi

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
        """Botni to'xtatishdan oldin oxirgi zaxirani majburan yuklaydi."""
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
        if self.last_error:
            return f"💾 Zaxira: ⚠️ <b>xato</b> — {self.last_error}"
        if self.last_success:
            return f"💾 Zaxira: ✅ {self.last_success}"
        return "💾 Zaxira: yoqilgan, hali yuborilmagan"


# Butun ilova uchun bitta nusxa
backup = GitHubBackup()
