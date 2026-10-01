"""Exports of the panel (S9: EXP-1, EXP-2, EXP-3, SEC-8, L10N-2; 02_feature_catalog.md).

The builders run inside a `ts.job` for the member who asked and only produce what that member may see at the moment of
running: client rows follow the relationship rules, result rows follow `ts.assignment.result_level`. Raw answers, item texts,
scoring keys and the free-text field names of TALENT-INV-15 are never exported. Files are UTF-8 with a BOM, digits are
Latin, every date comes twice (Jalali and ISO) and cells that a spreadsheet would read as a formula are prefixed with `'`.
"""
import csv
import io
from datetime import datetime, time
from zoneinfo import ZoneInfo

from odoo.addons.ts_assessment.models.attempt import jalali

LATIN = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
FORMULA_START = ('=', '+', '-', '@', '\t', '\r')
TEHRAN = ZoneInfo('Asia/Tehran')
TALENT_CODE = 'TALENT-INV-15'
SCALES = ('ANA', 'EXP', 'ACA', 'NOV', 'DUT')

CLIENT_HEADERS = ['نام', 'کد', 'گروه‌ها', 'مسئول', 'وضعیت', 'دعوت باز', 'تکمیل‌شده', 'آخرین فعالیت (شمسی)', 'آخرین فعالیت (میلادی)']
STATUS_HEADERS = ['نام', 'کد', 'سنجه', 'وضعیت', 'تاریخ دعوت (شمسی)', 'تاریخ دعوت (میلادی)', 'مهلت (شمسی)', 'مهلت (میلادی)',
                  'تاریخ تکمیل (شمسی)', 'تاریخ تکمیل (میلادی)']
RESULT_HEADERS = ['نام', 'کد', 'سنجه', 'عامل یا شمارهٔ زمینه', 'سطح', 'تحلیل‌گری', 'کاوش‌گری', 'علمی', 'نوآوری', 'وظیفه‌شناسی', 'کل']


def safe(v):
    """One cell: None -> '', numbers stay numbers, text is Latin-digit and formula-safe (SEC-8)."""
    if v is None or v is False:
        return ''
    if isinstance(v, (int, float)):
        return v
    s = str(v).translate(LATIN)
    return "'" + s if s.startswith(FORMULA_START) else s


def date_cols(value):
    """(Jalali, ISO) for a Datetime (UTC) or a Date; both empty for no value."""
    if not value:
        return '', ''
    if isinstance(value, datetime):
        local = value.replace(tzinfo=ZoneInfo('UTC')).astimezone(TEHRAN)
        return jalali(value, with_time=False).translate(LATIN), local.date().isoformat()
    dt = datetime.combine(value, time(12, 0))     # a plain date: noon avoids a day shift in the zone conversion
    return jalali(dt, with_time=False).translate(LATIN), value.isoformat()


def to_csv(headers, rows):
    out = io.StringIO()
    w = csv.writer(out, lineterminator='\r\n')
    w.writerow([safe(h) for h in headers])
    for r in rows:
        w.writerow([safe(c) for c in r])
    return b'\xef\xbb\xbf' + out.getvalue().encode('utf-8')


def to_xlsx(headers, rows):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.sheet_view.rightToLeft = True
    ws.append([safe(h) for h in headers])
    for r in rows:
        ws.append([safe(c) for c in r])
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = 's'            # never a formula, whatever the text looks like
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def render(fmt, headers, rows):
    """-> (bytes, extension, mimetype)"""
    if fmt == 'xlsx':
        return to_xlsx(headers, rows), 'xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return to_csv(headers, rows), 'csv', 'text/csv'


# ---------------------------------------------------------------------- row builders (one per job kind)
def _client_domain(member, params):
    from ..controllers.clients import visible_domain          # lazy: the controllers import the models
    dom = visible_domain(member)
    st = params.get('state') or 'active'
    if st in ('active', 'archived'):
        dom = dom + [('state', '=', st)]
    if params.get('group_id'):
        dom = dom + [('group_ids', 'in', [int(params['group_id'])])]
    return dom


def client_rows(env, member, params):
    C = env['ts.panel.client'].sudo()
    dom = _client_domain(member, params)
    labels = dict(C._fields['state'].selection)
    rows = []
    for c in C.search(dom, order='name, id'):
        j, i = date_cols(c.last_activity_at)
        rows.append([c.name, c.code, '، '.join(c.group_ids.mapped('name')), c.responsible_id.user_id.name or '',
                     labels.get(c.state, c.state), c.open_count, c.done_count, j, i])
    return CLIENT_HEADERS, rows


def _assignment_domain(member, params):
    from ..controllers.invites import assignment_domain
    dom = assignment_domain(member) + [('client_id', '!=', False)]
    if params.get('instrument_id'):
        dom = dom + [('instrument_id', '=', int(params['instrument_id']))]
    if params.get('group_id'):
        dom = dom + [('client_id.group_ids', 'in', [int(params['group_id'])])]
    return dom


def _assignments(env, member, params):
    return env['ts.assignment'].sudo().search(_assignment_domain(member, params), order='client_id, id')


def count_rows(env, member, kind, params):
    """Cheap size estimate that decides between running at once and queueing."""
    if kind == 'export_clients':
        return env['ts.panel.client'].sudo().search_count(_client_domain(member, params))
    return env['ts.assignment'].sudo().search_count(_assignment_domain(member, params))


def status_rows(env, member, params):
    A = env['ts.assignment'].sudo()
    labels = dict(A._fields['state'].selection)
    rows = []
    for a in _assignments(env, member, params):
        c = a.client_id
        j1, i1 = date_cols(a.create_date)
        j2, i2 = date_cols(a.deadline)
        j3, i3 = date_cols(a.attempt_id.submitted_at if a.state == 'done' else False)
        rows.append([c.name, c.code, a.instrument_id.name, labels.get(a.state, a.state), j1, i1, j2, i2, j3, i3])
    return STATUS_HEADERS, rows


def result_rows(env, member, params):
    """Only completed, released results at the level this member holds; band per factor, or the five scale scores per
    field for TALENT-INV-15. A clinical or benefits panel has no such export (the job refuses before this point)."""
    band_fa = {'low': 'کم', 'mid': 'متوسط', 'high': 'زیاد'}
    rows = []
    for a in _assignments(env, member, params):
        if a.state != 'done' or a.purpose not in ('education', 'employment'):
            continue
        level = a.result_level(member)
        if level not in ('summary', 'education'):
            continue
        c, at = a.client_id, a.attempt_id
        if a.instrument_id.code == TALENT_CODE:
            if level != 'education':
                continue
            prof = at.ts_profile()
            for n, f in enumerate(prof.get('fields', []), 1):
                sc = f.get('scales', {})
                rows.append([c.name, c.code, a.instrument_id.name, n, '', *[round(sc.get(k, 0), 1) for k in SCALES],
                             round(f.get('composites', {}).get('TOT', 0), 1)])
        else:
            for r in at.result_rows():
                rows.append([c.name, c.code, a.instrument_id.name, r.factor_id.name, r.band_fa() or band_fa.get(r.band, ''),
                             '', '', '', '', '', ''])
    return RESULT_HEADERS, rows
