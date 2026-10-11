"""Solar Hijri (Jalali) date helpers for website 4 forms. Pure Python, no Odoo import, no library.

CONTRACT (shared component, used by every module that shows a date field):

    QWeb  <t t-call="ts_website.jdate" jd_name.f="deadline" jd_id.f="inv_deadline" jd_label.f="مهلت پاسخ"
             jd_value="False or '2026-10-12'" jd_hint.f="اختیاری" jd_required="True"/>
          (static strings take the .f suffix; a plain attribute is evaluated as an expression)
      posts two fields:  deadline          ISO yyyy-mm-dd, filled by ts_nav.js (empty without JavaScript)
                         deadline_jalali   what the person typed, e.g. «۱۴۰۵/۰۷/۲۰» (Persian or Latin digits)

    Python  from odoo.addons.ts_website.tools import parse_jdate
            d = parse_jdate(post.get('deadline'), post.get('deadline_jalali'))   # -> datetime.date or None

parse_jdate trusts the visible Jalali text first (it is what the person sees, with or without JavaScript); when the
form did not post a Jalali field at all (None), it falls back to the ISO value. An empty or invalid Jalali text gives
None; the caller decides whether the field is required and shows its own error.
"""
import datetime
import re

FA_DIGITS = '۰۱۲۳۴۵۶۷۸۹'
AR_DIGITS = '٠١٢٣٤٥٦٧٨٩'
MONTHS = ('فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
          'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند')
_TO_LATIN = {ord(c): str(i) for i, c in enumerate(FA_DIGITS)}
_TO_LATIN.update({ord(c): str(i) for i, c in enumerate(AR_DIGITS)})


def gregorian_to_jalali(gy, gm, gd):
    g_d_m = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def jalali_to_gregorian(jy, jm, jd):
    jy += 1595
    days = -355668 + 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd
    days += (jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    month_days = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    gm = 0
    while gm < 12 and gd > month_days[gm]:
        gd -= month_days[gm]
        gm += 1
    return gy, gm + 1, gd


def jalali_date(value):
    """'۱۴۰۵/۰۷/۲۰' (or 1405-7-20, 05/7/20) -> datetime.date, None when it is not a real Jalali date."""
    if not value:
        return None
    s = str(value).translate(_TO_LATIN).strip()
    parts = [p for p in re.split(r'[\s/\-.،,]+', s) if p]
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    jy, jm, jd = (int(p) for p in parts)
    if jy < 100:
        jy += 1400 if jy < 50 else 1300
    if not (1 <= jm <= 12 and 1 <= jd <= 31) or not (1300 <= jy <= 1500):
        return None
    try:
        g = datetime.date(*jalali_to_gregorian(jy, jm, jd))
    except ValueError:
        return None
    if gregorian_to_jalali(g.year, g.month, g.day) != (jy, jm, jd):   # 31 Mehr, 30 Esfand of a common year ...
        return None
    return g


def fa(value):
    return str(value).translate(str.maketrans('0123456789', FA_DIGITS))


def format_jalali(value, words=False):
    """date / datetime / ISO string -> '۱۴۰۵/۰۷/۲۰' (words=True: '۲۰ مهر ۱۴۰۵'); '' for an empty or bad value."""
    if not value:
        return ''
    if isinstance(value, str):
        try:
            value = datetime.date.fromisoformat(value[:10])
        except ValueError:
            return ''
    jy, jm, jd = gregorian_to_jalali(value.year, value.month, value.day)
    if words:
        return fa('%d %s %d' % (jd, MONTHS[jm - 1], jy))
    return fa('%04d/%02d/%02d' % (jy, jm, jd))


def parse_jdate(value_iso, value_jalali):
    """The date a ts_website.jdate field posted -> datetime.date or None (see the contract above)."""
    if value_jalali is not None:
        return jalali_date(value_jalali)
    if not value_iso:
        return None
    try:
        return datetime.date.fromisoformat(str(value_iso).strip()[:10])
    except ValueError:
        return None
