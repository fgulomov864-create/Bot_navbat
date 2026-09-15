"""Tipli callback_data fabrikalari.

Eski kodda callback_data qo'lda string sifatida yig'ilib, split('_') bilan ajratilardi —
bu xatoga moyil edi. Endi aiogram'ning CallbackData factory'si ishlatiladi.

Ajratuvchi sifatida '|' tanlangan, chunki soat ('09:00') ichida ':' bor va u
standart ajratuvchi bilan to'qnashardi.
"""

from aiogram.filters.callback_data import CallbackData


class DeptCB(CallbackData, prefix="dept", sep="|"):
    """Bo'lim tanlandi -> kunlar ro'yxati."""
    key: str


class DateCB(CallbackData, prefix="date", sep="|"):
    """Kun tanlandi -> soatlar ro'yxati."""
    key: str
    date: str


class SlotCB(CallbackData, prefix="slot", sep="|"):
    """Soat tanlandi -> navbat yoziladi."""
    key: str
    date: str
    time: str


class UserBookingCB(CallbackData, prefix="ub", sep="|"):
    """Bemorning o'z navbati ustidagi amali (hozircha: bekor qilish)."""
    action: str  # cancel | confirm_cancel
    id: int


class NavCB(CallbackData, prefix="nav", sep="|"):
    """Oddiy navigatsiya: ortga, yopish, band soat."""
    to: str  # depts | close | busy | noop


class AdminCB(CallbackData, prefix="adm", sep="|"):
    """Admin panel menyusi."""
    action: str  # menu | queue | stats | admins | passwd | logout | logout_yes
    page: int = 0


class AdminUserCB(CallbackData, prefix="admu", sep="|"):
    """Adminlar ro'yxatidagi amallar."""
    action: str  # del_ask | del_yes
    user_id: int


class AdminQueueCB(CallbackData, prefix="admq", sep="|"):
    """Admin panelidagi bitta navbat ustidagi amallar."""
    action: str  # notify | done | missed | cancel
    id: int
    page: int = 0


class AdminDeptCB(CallbackData, prefix="admdept", sep="|"):
    """Bo'limlarni tahrirlash (faqat super admin)."""
    action: str  # open | rename | times | del_ask | del_yes | add | up | down
    key: str = ""


class AdminSetCB(CallbackData, prefix="admset", sep="|"):
    """Navbat qoidalari va klinika ma'lumotlarini tahrirlash."""
    action: str  # days | max | lead | weekday | address | maplink | reset_ask | reset_yes
    value: int = -1
