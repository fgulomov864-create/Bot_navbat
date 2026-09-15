"""Routerlar ro'yxati.

TARTIB MUHIM: aiogram routerlarni shu ketma-ketlikda tekshiradi.
`fallback` har doim eng oxirida turishi kerak, aks holda u barcha xabarlarni yutib yuboradi.
"""

from aiogram import Router

from handlers import admin, booking, common, fallback


def setup_routers() -> Router:
    root = Router(name="root")
    root.include_router(common.router)
    root.include_router(admin.router)
    root.include_router(booking.router)
    root.include_router(fallback.router)
    return root
