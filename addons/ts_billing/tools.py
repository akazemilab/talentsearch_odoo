"""Money and calendar helpers of ts_billing (no Odoo import)."""
from datetime import datetime, time
from zoneinfo import ZoneInfo

from odoo.addons.ts_website.tools import gregorian_to_jalali, jalali_to_gregorian

TEHRAN = ZoneInfo('Asia/Tehran')
UTC = ZoneInfo('UTC')
_FA = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')
SEP = '٬'      # Arabic thousands separator «٬»

# Roles whose invitations a monthly cap can limit (never owner/admin/clinic_director/hr_admin).
CAPPED_ROLES = ('clinician', 'counselor', 'hiring_manager', 'reviewer')

# Who holds credits:read / credits:manage, by panel purpose (role labels of the glossary §3; «مدیر پنل» is not a role).
_CREDIT_ROLES = {
    'clinical': ('مالک', 'هماهنگ‌کننده', 'مدیر مرکز مشاوره'),
    'employment': ('مالک', 'هماهنگ‌کننده', 'مدیر منابع انسانی'),
    'benefits': ('مالک', 'هماهنگ‌کننده', 'مدیر منابع انسانی'),
}
_CREDIT_ASK = {'clinical': 'مالک یا مدیر مرکز مشاوره', 'employment': 'مالک یا مدیر منابع انسانی',
               'benefits': 'مالک یا مدیر منابع انسانی'}


def credit_roles(purpose, conj='و'):
    """«مالک، هماهنگ‌کننده و مدیر مرکز مشاوره» (conj «و» or «یا»): every role that manages the panel's credit."""
    roles = _CREDIT_ROLES.get(purpose, ('مالک', 'هماهنگ‌کنندهٔ پنل'))
    return '%s %s %s' % ('، '.join(roles[:-1]), conj, roles[-1])


def credit_ask(purpose):
    """Whom a counselor asks for a top-up or a higher cap: «مالک یا مدیر مرکز مشاوره»."""
    return _CREDIT_ASK.get(purpose, 'مالک یا هماهنگ‌کنندهٔ پنل')


def item_title(rec):
    """Display name of an instrument or battery: ts_display_title() when the catalog offers it, else the catalog title."""
    if not rec:
        return ''
    if hasattr(rec, 'ts_display_title'):
        return rec.ts_display_title()
    return ('title' in rec._fields and rec.title) or rec.name


def rial_int(x):
    """Round a Rial value to an integer (half away from zero)."""
    x = float(x or 0)
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def round10(x):
    """Round a Rial value to a multiple of 10 (so the toman amount is an integer)."""
    r = rial_int(x)
    return int(round(r / 10.0)) * 10


def fa_num(n):
    """1200000 -> «۱٬۲۰۰٬۰۰۰»."""
    n = int(n)
    s = '{:,}'.format(abs(n)).replace(',', SEP).translate(_FA)
    return ('-' + s) if n < 0 else s


def fmt_toman(rial):
    """Rial -> «۱٬۲۰۰٬۰۰۰ تومان». Prices are multiples of 10 Rial; anything else is rounded to the nearest toman."""
    return '%s تومان' % fa_num(rial_int(rial_int(rial) / 10.0))


def toman_num(rial):
    """Rial -> «۱۲۰٬۰۰۰» (toman, no unit)."""
    return fa_num(rial_int(rial_int(rial) / 10.0))


def jalali_month_bounds(now=None):
    """(start, end) of the current Jalali month in Asia/Tehran, as naive UTC datetimes (end exclusive)."""
    now = (now or datetime.now(UTC)).astimezone(TEHRAN)
    jy, jm, _jd = gregorian_to_jalali(now.year, now.month, now.day)
    ny, nm = (jy + 1, 1) if jm == 12 else (jy, jm + 1)

    def utc_of(y, m):
        gy, gm, gd = jalali_to_gregorian(y, m, 1)
        local = datetime.combine(datetime(gy, gm, gd).date(), time(0, 0), tzinfo=TEHRAN)
        return local.astimezone(UTC).replace(tzinfo=None)
    return utc_of(jy, jm), utc_of(ny, nm)
