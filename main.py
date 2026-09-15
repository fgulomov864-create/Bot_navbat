"""Stomatologiya klinikasi navbat boti — kirish nuqtasi.

Ishga tushirish:
    python main.py
"""

import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

import storage as db
from config import ADMIN_ID, BASE_DIR, BOT_TOKEN, DEFAULT_ADMIN_PASSWORD
from handlers import setup_routers
from handlers.errors import on_error

log = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="🤖 Botni qayta ishga tushirish"),
    BotCommand(command="help", description="ℹ️ Yordam"),
    BotCommand(command="cancel", description="🔙 Joriy amaldan chiqish"),
    BotCommand(command="admin", description="👨‍⚕️ Admin panel"),
]


def setup_logging() -> None:
    """Loglash eng birinchi sozlanadi — ishga tushish paytidagi xatolar ham yozilsin."""
    # Windows konsoli standart holatda cp1252 — emoji chiqarishda UnicodeEncodeError beradi.
    # Shuning uchun chiqishni majburan UTF-8 ga o'tkazamiz.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    log_file = BASE_DIR / "bot.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"),
        ],
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def on_startup(bot: Bot) -> None:
    await db.connect()

    # .env da ADMIN_ID ko'rsatilgan bo'lsa, u avtomatik super admin bo'ladi
    if ADMIN_ID and not await db.is_admin(ADMIN_ID):
        await db.add_admin(ADMIN_ID, "Asosiy admin", None, force_super=True)
        log.info(".env dagi ADMIN_ID super admin sifatida qo'shildi: %s", ADMIN_ID)

    if await db.count_admins() == 0:
        log.warning(
            "Hali birorta admin yo'q. /admin buyrug'ini bosib parolni kiriting — "
            "birinchi kirgan odam SUPER ADMIN bo'ladi. Boshlang'ich parol: %s",
            DEFAULT_ADMIN_PASSWORD,
        )

    await bot.set_my_commands(COMMANDS)
    me = await bot.get_me()
    log.info("Bot ishga tushdi: @%s", me.username)


async def on_shutdown() -> None:
    await db.close()
    log.info("Bot to'xtatildi")


async def main() -> None:
    setup_logging()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(setup_routers())
    dp.errors.register(on_error)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    try:
        # Bot o'chiq turgan paytdagi eski xabarlarni tashlab yuborish
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.getLogger(__name__).info("Bot qo'lda to'xtatildi")
