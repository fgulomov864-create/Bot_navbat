"""Umumiy yordamchi funksiyalar: vaqt zonasi, sana formatlash, HTML tozalash."""

import html
from datetime import date, datetime, timedelta

from config import MIN_LEAD_MINUTES, TIMEZONE, WEEKDAYS_UZ

DATE_FMT = "%Y-%m-%d"


def now() -> datetime:
    """Klinika vaqt zonasidagi hozirgi vaqt (server UTC'da bo'lsa ham to'g'ri ishlaydi)."""
    return datetime.now(TIMEZONE)


def today_str() -> str:
    return now().strftime(DATE_FMT)


def to_date(date_str: str) -> date:
    return datetime.strptime(date_str, DATE_FMT).date()


def slot_datetime(date_str: str, time_str: str) -> datetime:
    """'2026-09-16' + '09:00' -> vaqt zonasi bilan datetime."""
    naive = datetime.strptime(f"{date_str} {time_str}", f"{DATE_FMT} %H:%M")
    return naive.replace(tzinfo=TIMEZONE)


def is_slot_bookable(date_str: str, time_str: str) -> bool:
    """Bu vaqtga hali navbat olish mumkinmi (o'tib ketmaganmi)."""
    return slot_datetime(date_str, time_str) - timedelta(minutes=MIN_LEAD_MINUTES) > now()


def weekday_name(d: date) -> str:
    return WEEKDAYS_UZ[d.weekday()]


def pretty_date(date_str: str) -> str:
    """'2026-09-16' -> '16.09.2026 (Chorshanba)'."""
    try:
        d = to_date(date_str)
    except ValueError:
        return date_str
    return f"{d.strftime('%d.%m.%Y')} ({weekday_name(d)})"


def esc(value) -> str:
    """HTML parse_mode uchun matnni xavfsizlantirish.

    Bemor ismida '<', '&' yoki Markdown belgilari bo'lsa ham xabar buzilmaydi.
    """
    return html.escape(str(value if value is not None else "—"), quote=False)


def user_label(full_name: str | None, username: str | None = None) -> str:
    """Xabarlarda ko'rsatiladigan tozalangan foydalanuvchi nomi."""
    label = esc(full_name or "Noma'lum")
    if username:
        label += f" (@{esc(username)})"
    return label
