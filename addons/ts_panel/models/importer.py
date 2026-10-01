"""File import of clients (S8, IMP-1, SEC-4): parsing, mapping, validation, matching and applying.

Parsing and planning are plain functions so that they can be tested without a request. Nothing here writes row content
to a log or to the audit trail: the error report carries row numbers and reason codes only (never names, phones or
e-mail addresses). Matching is idempotent: an existing client is found by code, else by phone, else by e-mail, and
is updated; it is never duplicated.
"""
import codecs
import csv
import io
import re
import zipfile

from odoo.addons.ts_org.models.panel import norm_email, norm_phone

from .text import norm_text

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 2000
MAX_UNZIPPED = 20 * 1024 * 1024
FIELDS = [('name', 'نام'), ('code', 'کد'), ('phone', 'موبایل'), ('email', 'ایمیل'), ('group', 'گروه'), ('age_group', 'گروه سنی')]
TEMPLATE_HEADERS = [label for _k, label in FIELDS]
SYNONYMS = {
    'name': ('نام', 'نام و نام خانوادگی', 'نام ونام خانوادگی', 'اسم', 'name', 'full name', 'fullname'),
    'code': ('کد', 'شماره دانش آموزی', 'شماره پرونده', 'شماره', 'code', 'id', 'student id'),
    'phone': ('موبایل', 'تلفن', 'تلفن همراه', 'شماره موبایل', 'همراه', 'phone', 'mobile', 'cell'),
    'email': ('ایمیل', 'پست الکترونیک', 'email', 'e-mail', 'mail'),
    'group': ('گروه', 'کلاس', 'کلاس درس', 'group', 'class'),
    'age_group': ('گروه سنی', 'سن', 'سنی', 'age group', 'age'),
}
_ARABIC_FORMS = str.maketrans('يكى', 'یکی')   # Arabic yeh/kaf/alef maksura -> Persian forms
_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
_ADULT = ('adult', 'بزرگسال', 'بالغ', 'بزرگ')
_MINOR = ('minor', 'زیر 18', 'زیر ۱۸', 'کودک', 'نوجوان', 'دانش آموز', 'دانش‌آموز', 'کم سن')

ERRORS = {
    'name': 'نام خالی است یا بیش از ۱۲۰ نویسه دارد',
    'phone': 'شمارهٔ موبایل معتبر نیست',
    'email': 'ایمیل معتبر نیست',
    'code': 'کد بیش از ۴۰ نویسه دارد',
    'age': 'گروه سنی را نشناختیم (بزرگسال یا زیر ۱۸)',
    'dup_file': 'همین کد، موبایل یا ایمیل پیش‌تر در همین فایل آمده است',
    'conflict': 'کد، موبایل و ایمیل این ردیف به دو شرکت‌کنندهٔ متفاوت می‌خورد',
    'locked': 'اطلاعات این فرد از دادهٔ تاریخی است و قفل است',
    'archived': 'این شرکت‌کننده بایگانی شده است',
}

FILE_ERRORS = {
    'ext': 'فقط فایل csv یا xlsx پذیرفته می‌شود.',
    'size': 'حجم فایل بیش از ۲ مگابایت است.',
    'empty': 'فایل خالی است یا ردیف سرستون ندارد.',
    'rows': 'فایل بیش از ۲۰۰۰ ردیف دارد؛ آن را به چند فایل تقسیم کنید.',
    'binary': 'محتوای فایل متن csv یا کاربرگ xlsx نیست.',
    'encoding': 'کدگذاری فایل خوانده نشد؛ آن را با UTF-8 ذخیره کنید.',
    'xlsx': 'فایل xlsx خوانده نشد.',
    'forbidden': 'دسترسی شما برای این کار دیگر معتبر نیست.',
    'no_name': 'ستونی برای «نام» تطبیق داده نشده است.',
}


class FileProblem(Exception):
    """A file-level problem. `code` is shown as a Persian message by the controller."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def fix_digits(text):
    return (text or '').translate(_DIGITS)


def decode_bytes(data):
    return _decode_raw(data).translate(_ARABIC_FORMS)


def _decode_raw(data):
    if data.startswith(codecs.BOM_UTF8):
        return data.decode('utf-8-sig')
    if data[:2] in (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE):
        return data.decode('utf-16')
    if b'\x00' in data:
        raise FileProblem('binary')
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        pass
    try:
        return data.decode('cp1256')
    except UnicodeDecodeError:
        raise FileProblem('encoding')


def _cell(v):
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).translate(_ARABIC_FORMS).strip()


def parse_table(data, filename):
    """Returns (headers, rows) as lists of strings; raises FileProblem for any file-level problem."""
    name = (filename or '').lower()
    if not (name.endswith('.csv') or name.endswith('.xlsx')):
        raise FileProblem('ext')
    if len(data) > MAX_BYTES:
        raise FileProblem('size')
    if not data.strip():
        raise FileProblem('empty')
    table = _parse_xlsx(data) if name.endswith('.xlsx') else _parse_csv(data)
    table = [r for r in table if any((c or '').strip() for c in r)]
    if not table:
        raise FileProblem('empty')
    headers, rows = [c.strip() for c in table[0]], table[1:]
    if len(rows) > MAX_ROWS:
        raise FileProblem('rows')
    return headers, rows


def _parse_csv(data):
    text = decode_bytes(data)
    first = text.split('\n', 1)[0]
    delim = max((',', ';', '\t'), key=lambda d: first.count(d))
    if not first.count(delim):
        delim = ','
    return [[c.strip() for c in row] for row in csv.reader(io.StringIO(text), delimiter=delim)]


def _parse_xlsx(data):
    if data[:4] != b'PK\x03\x04':
        raise FileProblem('binary')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
                raise FileProblem('size')
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        out = []
        for row in wb.worksheets[0].iter_rows(values_only=True):
            out.append([_cell(c) for c in row])
            if len(out) > MAX_ROWS + 1:
                break
        wb.close()
        return out
    except FileProblem:
        raise
    except Exception:
        raise FileProblem('xlsx')


def auto_map(headers):
    """{column index: field} by header text; a field is used once."""
    lookup = {}
    for field, names in SYNONYMS.items():
        for n in names:
            lookup[norm_text(fix_digits(n))] = field
    taken, out = set(), {}
    for i, h in enumerate(headers):
        f = lookup.get(norm_text(fix_digits(h)))
        if f and f not in taken:
            out[i] = f
            taken.add(f)
    return out


def _age(v):
    t = norm_text(fix_digits(v or ''))
    if not t:
        return 'unknown'
    if t in {norm_text(x) for x in _ADULT}:
        return 'adult'
    if t in {norm_text(x) for x in _MINOR}:
        return 'minor'
    return None


def clean_row(raw, mapping):
    """Row values -> ({field: value}, error code or None)."""
    v = {field: ((raw[idx] if idx < len(raw) else '') or '').strip() for idx, field in mapping.items()}
    out = {'name': ' '.join(v.get('name', '').split()), 'code': fix_digits(v.get('code', '')).strip(),
           'phone': v.get('phone', ''), 'email': v.get('email', ''), 'groups': [], 'age_group': 'unknown'}
    if not 2 <= len(out['name']) <= 120:
        return out, 'name'
    if len(out['code']) > 40:
        return out, 'code'
    if out['phone']:
        ph = norm_phone(out['phone'])
        if not ph:
            return out, 'phone'
        out['phone'] = ph
    if out['email']:
        em = norm_email(out['email'])
        if not em:
            return out, 'email'
        out['email'] = em
    age = _age(v.get('age_group'))
    if age is None:
        return out, 'age'
    out['age_group'] = age
    if v.get('group'):
        out['groups'] = [g for g in dict.fromkeys(' '.join(x.split())[:60] for x in re.split(r'[|؛;،]', v['group'])) if g]
    return out, None


def plan(env, ws_id, rows, mapping):
    """Decide per row: create / update / same / error. Reads the panel's clients once; writes nothing."""
    C = env['ts.panel.client'].sudo().with_context(active_test=False)
    existing = C.search([('workspace_id', '=', int(ws_id))])
    index = {'code': {c.code: c for c in existing if c.code},
             'phone': {c.phone: c for c in existing if c.phone and c.state == 'active'},
             'email': {c.email: c for c in existing if c.email and c.state == 'active'}}
    seen = {'code': set(), 'phone': set(), 'email': set()}
    out = []
    for n, raw in enumerate(rows, start=2):
        vals, err = clean_row(raw, mapping)
        item = {'n': n, 'vals': vals, 'action': 'error', 'err': err, 'client_id': False}
        out.append(item)
        if err:
            continue
        keys = [(k, vals[k]) for k in ('code', 'phone', 'email') if vals[k]]
        if any(val in seen[k] for k, val in keys):
            item['err'] = 'dup_file'
            continue
        for k, val in keys:
            seen[k].add(val)
        hits = []
        for k, val in keys:
            c = index[k].get(val)
            if c and c not in hits:
                hits.append(c)
        if len(hits) > 1:
            item['err'] = 'conflict'
            continue
        if not hits:
            item['action'], item['err'] = 'create', None
            continue
        c = hits[0]
        if c.state != 'active':
            item['err'] = 'archived'
            continue
        if c.contact_locked:
            item['err'] = 'locked'
            continue
        item['client_id'] = c.id
        changes = {}
        if vals['name'] != c.name:
            changes['name'] = vals['name']
        for k in ('code', 'phone', 'email'):
            if vals[k] and vals[k] != c[k]:
                other = index[k].get(vals[k])
                if other and other != c:
                    item['err'] = 'conflict'
                    break
                changes[k] = vals[k]
        if item['err']:
            continue
        if vals['age_group'] != 'unknown' and vals['age_group'] != c.age_group:
            changes['age_group'] = vals['age_group']
        have = {g.name_norm for g in c.group_ids}
        new_groups = [g for g in vals['groups'] if norm_text(g) not in have]
        if new_groups:
            changes['groups'] = new_groups
        item['changes'] = changes
        item['action'], item['err'] = ('update' if changes else 'same'), None
    return out


def summarize(items):
    s = {'create': 0, 'update': 0, 'same': 0, 'error': 0}
    for it in items:
        s[it['action']] += 1
    return s


def apply_plan(env, ws, user_id, items, commit=None, batch=200):
    """Write the planned creates and updates. `commit` is a callable (the runner passes cr.commit; tests pass nothing)."""
    C = env['ts.panel.client'].sudo()
    G = env['ts.panel.group'].sudo()
    groups = {g.name_norm: g for g in G.search([('workspace_id', '=', ws.id), ('active', '=', True)])}
    resp = env['ts.workspace.member'].sudo().ts_panel_default_responsible(ws.id, user_id)

    def group_ids(names):
        ids = []
        for name in names:
            key = norm_text(name)
            g = groups.get(key)
            if not g:
                g = groups[key] = G.create({'workspace_id': ws.id, 'name': name, 'kind': 'class'})
            ids.append(g.id)
        return ids

    done = 0
    result = {'create': 0, 'update': 0, 'same': 0, 'error': 0}
    for it in items:
        if it['action'] == 'create':
            v = it['vals']
            C.create({'workspace_id': ws.id, 'name': v['name'], 'code': v['code'] or False, 'phone': v['phone'] or False,
                      'email': v['email'] or False, 'age_group': v['age_group'], 'source': 'csv',
                      'responsible_id': resp.id or False, 'group_ids': [(6, 0, group_ids(v['groups']))]})
        elif it['action'] == 'update':
            ch = dict(it['changes'])
            names = ch.pop('groups', [])
            if names:
                ch['group_ids'] = [(4, gid) for gid in group_ids(names)]
            C.browse(it['client_id']).write(ch)
        result[it['action']] += 1
        done += 1
        if commit and done % batch == 0:
            env.flush_all()
            commit()
    return result


def error_report(items):
    """CSV text: row number and reason only. No names, phones, e-mail addresses or codes."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['ردیف', 'علت'])
    for it in items:
        if it['action'] == 'error':
            w.writerow([it['n'], ERRORS.get(it['err'], it['err'])])
    return '﻿' + out.getvalue()


def template_csv():
    out = io.StringIO()
    csv.writer(out).writerow(TEMPLATE_HEADERS)
    return '﻿' + out.getvalue()
