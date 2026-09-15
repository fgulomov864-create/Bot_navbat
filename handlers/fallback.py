"""Tushunilmagan xabarlar uchun oxirgi handler.

Eski kodda menyudan tashqari matnga bot umuman javob bermasdi.
Bu router HAMMA routerlardan KEYIN ulanishi shart.
"""

import logging

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import storage as db
import keyboards as kb

log = logging.getLogger(__name__)
router = Router(name="fallback")


@router.message()
async def unknown_message(message: Message, state: FSMContext) -> None:
    await state.clear()
    is_admin = await db.is_admin(message.from_user.id)
    await message.answer(
        "🤔 Buni tushunmadim.\n\nQuyidagi menyudan foydalaning yoki /help ni bosing:",
        reply_markup=kb.main_menu(is_admin),
    )


@router.callback_query()
async def unknown_callback(callback: CallbackQuery) -> None:
    """Bot qayta ishga tushgandan keyin eski xabardagi tugma bosilsa."""
    log.info("Noma'lum callback: %s (user_id=%s)", callback.data, callback.from_user.id)
    await callback.answer("Bu tugma eskirgan. /start ni bosing.", show_alert=True)
