"""Global xato ushlagich.

Shusiz handler ichidagi har qanday kutilmagan xato faqat log'ga tushib,
foydalanuvchi hech qanday javob olmasdi — bot "o'lik" ko'rinardi.

Bu handler main.py da to'g'ridan-to'g'ri Dispatcher'ga ulanadi,
shuning uchun barcha routerlardagi xatolarni ushlaydi.
"""

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ErrorEvent

log = logging.getLogger(__name__)

USER_MESSAGE = "⚠️ Kutilmagan xatolik yuz berdi. Iltimos, /start ni bosib qayta urinib ko'ring."


async def on_error(event: ErrorEvent) -> bool:
    exception = event.exception

    # "message is not modified" — foydalanuvchi bir tugmani ikki marta bosgan, bu xato emas
    if isinstance(exception, TelegramBadRequest) and "message is not modified" in str(exception):
        return True

    log.exception("Handler xatosi: %s", exception, exc_info=exception)

    update = event.update
    try:
        if update.callback_query:
            await update.callback_query.answer(USER_MESSAGE, show_alert=True)
        elif update.message:
            await update.message.answer(USER_MESSAGE)
    except Exception:
        log.debug("Foydalanuvchini xato haqida ogohlantirib bo'lmadi")

    return True
