"""Umumiy yordamchi funksiyalar: vaqt zonasi, sana formatlash, HTML tozalash."""

import html
import re
from datetime import date, datetime, timedelta

from config import TIMEZONE, WEEKDAYS_UZ

DATE_FMT = "%Y-%m-%d"
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


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


def is_slot_bookable(date_str: str, time_str: str, lead_minutes: int = 30) -> bool:
    """Bu vaqtga hali navbat olish mumkinmi (o'tib ketmaganmi).

    lead_minutes — qabulgacha kamida qancha vaqt qolishi kerak.
    Qiymat sozlamalardan (storage.rule) uzatiladi, shuning uchun parametr —
    aks holda utils <-> storage aylanma importi hosil bo'lardi.
    """
    return slot_datetime(date_str, time_str) - timedelta(minutes=lead_minutes) > now()


def parse_times(raw: str) -> list[str] | None:
    """Admin kiritgan soatlar matnini ro'yxatga aylantiradi.

    '09:00, 10:30 12:00' yoki '9:00\\n10:30' -> ['09:00', '10:30', '12:00']
    Bitta ham noto'g'ri soat bo'lsa None qaytaradi.
    Takrorlar olib tashlanadi, natija tartiblanadi.
    """
    parts = [p.strip() for p in re.split(r"[,\s;]+", raw or "") if p.strip()]
    if not parts:
        return None

    times: set[str] = set()
    for part in parts:
        match = TIME_RE.match(part)
        if not match:
            return None
        times.add(f"{int(match.group(1)):02d}:{match.group(2)}")

    return sorted(times)


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
