"""Pure helpers for the historical import (no ORM, no I/O beyond the rows handed in).

Source: the FormAfzar export of the interactive talent inventory: 17 meta columns, then eight
blocks of 28 columns (field name, 15 answers, 12 derived columns). Only what the owner approved
is read; IP, browser, location, operators, payment and referral columns are never touched."""
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .text import clean_label, norm_label

META = {'id': 0, 'created': 3, 'first': 12, 'last': 13, 'email': 14, 'phone': 15}
META_HEADERS = ['شناسه', 'شناسه اختصاصی', 'اپراتور ثبت کننده', 'تاریخ ثبت', 'اپراتور ویرایش کننده', 'تاریخ ویرایش',
                'مشتری اصلی', 'آدرس اینترنتی', 'مرورگر', 'IP', 'موقعیت مکانی', 'پرداخت آنلاین', 'نام',
                'نام خانوادگی', 'ایمیل', 'موبایل', 'ارجاع از:']
BLOCKS = 8
BLOCK_WIDTH = 28
FIRST_BLOCK = 17
N_ITEMS = 15
N_COLUMNS = 247
_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
_PREFIX = re.compile(r'^\s*\d+\s*-\s*\d+\s*\)\s*')
_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def digits(s):
    return str(s).translate(_DIGITS)


def norm_phone(v):
    """'09121234567' / '9121234567' / '+98 912 ...' / '0098...' -> '+989121234567', else None."""
    if v is None:
        return None
    d = re.sub(r'\D', '', digits(v))
    if d.startswith('0098'):
        d = d[4:]
    elif d.startswith('98') and len(d) == 12:
        d = d[2:]
    elif d.startswith('0') and len(d) == 11:
        d = d[1:]
    return '+98' + d if len(d) == 10 and d.startswith('9') else None


def norm_email(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    return s if _EMAIL.match(s) else None


def j2g(jy, jm, jd):
    """Jalali -> Gregorian (inverse of ts_assessment.g2j, 33-year arithmetic)."""
    jy += 1595
    days = -355668 + (365 * jy) + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd + ((jm - 1) * 31 if jm < 7 else ((jm - 7) * 30) + 186)
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
    leap = 29 if ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0) else 28
    months = [0, 31, leap, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 13 and gd > months[gm]:
        gd -= months[gm]
        gm += 1
    return gy, gm, gd


def parse_stamp(s):
    """'1403/05/17 14:32' (Jalali, Asia/Tehran wall clock) -> naive UTC datetime, or None."""
    m = re.match(r'^\s*(\d{4})/(\d{1,2})/(\d{1,2})[ T]+(\d{1,2}):(\d{2})', digits(s or ''))
    if not m:
        return None
    jy, jm, jd, hh, mm = (int(x) for x in m.groups())
    gy, gm, gd = j2g(jy, jm, jd)
    local = datetime(gy, gm, gd, hh, mm, tzinfo=ZoneInfo('Asia/Tehran'))
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def strip_prefix(header):
    return _PREFIX.sub('', str(header or ''))


def check_header(header, item_texts):
    """Returns a list of problems (empty = the sheet is the expected export)."""
    bad = []
    if len(header) != N_COLUMNS:
        bad.append('columns %d != %d' % (len(header), N_COLUMNS))
        return bad
    if [str(h).strip() for h in header[:17]] != META_HEADERS:
        bad.append('meta headers differ')
    want = [norm_label(t) for t in item_texts]
    for k in range(BLOCKS):
        b = FIRST_BLOCK + BLOCK_WIDTH * k
        got = [norm_label(strip_prefix(header[b + 1 + i])) for i in range(N_ITEMS)]
        if got != want:
            bad.append('block %d statements differ' % (k + 1))
    return bad


def _text(v):
    return clean_label(digits(v)) if v is not None else ''


def parse_row(row):
    """One export row -> dict. Never raises on data problems: reasons are returned for counting."""
    first, last = _text(row[META['first']]), _text(row[META['last']])
    out = {'src_id': _text(row[META['id']]), 'created': parse_stamp(row[META['created']]),
           'name': ('%s %s' % (first, last)).strip(), 'phone': norm_phone(row[META['phone']]),
           'phone_given': row[META['phone']] not in (None, ''), 'email': norm_email(row[META['email']]),
           'email_given': row[META['email']] not in (None, ''), 'fields': [], 'skipped': []}
    seen = set()
    for k in range(BLOCKS):
        b = FIRST_BLOCK + BLOCK_WIDTH * k
        label = _text(row[b])
        raw = [row[b + 1 + i] for i in range(N_ITEMS)]
        if not label:
            out['skipped'].append((k + 1, 'unnamed'))
            continue
        vals = []
        for v in raw:
            s = digits(v).strip() if v is not None else ''
            vals.append(int(s) if s in ('1', '2', '3', '4', '5') else None)
        if any(v is None for v in vals):
            out['skipped'].append((k + 1, 'incomplete'))
            continue
        if norm_label(label) in seen:
            out['skipped'].append((k + 1, 'duplicate_label'))
            continue
        seen.add(norm_label(label))
        derived = []
        for j in range(6):  # 5 scales + total
            d = row[b + 16 + j]
            try:
                derived.append(float(digits(d)) if d not in (None, '') else None)
            except ValueError:
                derived.append(None)
        out['fields'].append({'block': k + 1, 'label': label, 'answers': vals, 'derived': derived})
    return out


def derived_matches(field, result_field, tol=1.0):
    """The export's rounded scale/total columns vs our engine (5 scales + TOT); None derived = not comparable."""
    mine = [result_field['scales'][c] for c in ('ANA', 'EXP', 'ACA', 'NOV', 'DUT')] + [result_field['composites']['TOT']]
    ok, compared = True, 0
    for m, d in zip(mine, field['derived']):
        if d is None:
            continue
        compared += 1
        if abs(m - d) > tol:
            ok = False
    return ok, compared
