#!/usr/bin/env python3
"""Panel v2 S4 (clients) over HTTP against a served CLONE:  ts_http_pv2_4.py DB PORT"""
import importlib.util, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell
TS = 'talentsearch.ir'
NAMES = ('owner', 'admin', 'c1', 'c2', 'hm', 'hmo', 'outsider')
L = {n: 'ts.pv2s4.%s.http@example.invalid' % n for n in NAMES}
pw = {u: ensure_user(u) for u in L.values()}
code = r'''
L = %r
def user(n): return env['res.users'].search([('login', '=', L[n])])
def panel(name, purpose):
    org = env['res.partner'].search([('name', '=', name)], limit=1) or env['res.partner'].create({'name': name, 'is_company': True})
    org.write({'is_company': True})
    ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create(
        {'name': name, 'purpose': purpose, 'partner_id': org.id})
    ws.write({'approved_on': '2026-01-01 00:00:00'}); ws.state = 'pilot'
    return ws
def member(ws, n, role):
    u = user(n)
    m = env['ts.workspace.member'].search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)]) or env['ts.workspace.member'].create(
        {'workspace_id': ws.id, 'user_id': u.id, 'role': role})
    if role in ('counselor', 'clinician'):
        m.write({'license_number': 'T-1', 'verification_state': 'verified'})
    return m
A = panel('پنل S4 آموزشی', 'education'); H = panel('پنل S4 استخدامی', 'employment')
mo = member(A, 'owner', 'owner'); member(A, 'admin', 'admin'); m1 = member(A, 'c1', 'counselor'); m2 = member(A, 'c2', 'counselor')
member(H, 'hmo', 'owner'); mh = member(H, 'hm', 'hiring_manager')
C = env['ts.panel.client']
if not C.search_count([('workspace_id', '=', A.id)]):
    for i in range(30):
        C.create({'workspace_id': A.id, 'name': 'مراجع شمارهٔ %%02d' %% i, 'responsible_id': m1.id if i %% 2 else False})
    C.create({'workspace_id': A.id, 'name': 'علیرضا کریمی', 'responsible_id': m1.id, 'code': 'S-100'})
    C.create({'workspace_id': A.id, 'name': 'مریم از کارشناس دو', 'responsible_id': m2.id})
    C.create({'workspace_id': A.id, 'name': 'بدون کارشناس'})
    p = env['res.partner'].create({'name': 'فرد تاریخی'})
    C.create({'workspace_id': A.id, 'name': 'فرد تاریخی', 'partner_id': p.id, 'source': 'import'})
    C.create({'workspace_id': A.id, 'name': 'بایگانی‌شده', 'state': 'archived'})
    C.create({'workspace_id': H.id, 'name': 'متقاضی من', 'responsible_id': mh.id})
    C.create({'workspace_id': H.id, 'name': 'متقاضی همکار'})
C.search([('name', 'in', ['علیرضا کریمی', 'مریم از کارشناس دو', 'بدون کارشناس', 'فرد تاریخی', 'متقاضی من'])]).write({'last_activity_at': __import__('odoo').fields.Datetime.now()})
env.cr.commit()
cid = lambda ws, n: C.search([('workspace_id', '=', ws.id), ('name', '=', n)], limit=1).id
print('IDS', A.id, H.id, cid(A, 'علیرضا کریمی'), cid(A, 'مریم از کارشناس دو'), cid(H, 'متقاضی من'), cid(A, 'فرد تاریخی'), m1.id, m2.id)
''' % L
out = shell(code)
mm = re.search(r'IDS (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)', out)
assert mm, out[-1500:]
A, H, K1, K2, KH, KI, M1, M2 = mm.groups()


def login(n):
    c = Client(TS)
    assert c.login(L[n], pw[L[n]]), n
    return c


def get(c, path):
    st, loc, body = c.req(path)
    return st, body


def post(c, path, data):
    d = dict(data); d['csrf_token'] = c.csrf(c.req('/web/login')[2])
    return c.req(path, d)


def tbl(page):
    m = re.search(r'<table.*?</table>', page, re.S)
    return m.group(0) if m else ''


def menu(page):
    return [re.sub(r'\s+', ' ', t).strip() for t in re.findall(r'<a[^>]*class="tsp-nav__item"[^>]*>(.*?)</a>', page, re.S)]


own = login('owner')
st, body = get(own, '/my/workspaces/%s/clients' % A)
check('owner opens the client list', st == 200 and body.count('<h1') == 1 and 'شرکت‌کنندگان' in menu(body), '%s %s' % (st, menu(body)))
check('table has a caption, scope headers and data-labels for the phone layout',
      '<caption' in body and 'scope="col"' in body and body.count('data-label=') >= 5 and 'tsp-table--cards' in body)
check('owner sees everyone, imported and unassigned included', all(w in tbl(body) for w in ('علیرضا کریمی', 'مریم از کارشناس دو', 'بدون کارشناس', 'فرد تاریخی')))
check('archived people are not in the default list', 'بایگانی‌شده' not in tbl(body))
check('page 1 of 2 with a next link', 'rel="next"' in body)
st, body2 = get(own, '/my/workspaces/%s/clients?page=2' % A)
check('page 2 opens and has a previous link', st == 200 and 'rel="prev"' in body2)
check('page beyond the end is clamped, not an error', get(own, '/my/workspaces/%s/clients?page=999' % A)[0] == 200)
check('unknown sort or filter does not break', get(own, '/my/workspaces/%s/clients?sort=__import__&dir=x&filter=zzz' % A)[0] == 200)
st, body = get(own, '/my/workspaces/%s/clients?sort=name&dir=asc' % A)
names = re.findall(r'class="tsp-table.*?</table>', body, re.S)
check('sorted by name ascending: aria-sort says so', 'aria-sort="ascending"' in body)

# search keeps the text out of the URL, folds Arabic letters
st, loc, _ = post(own, '/my/workspaces/%s/clients' % A, {'q': 'عليرضا', 'filter': 'all'})
check('search POST redirects without the text in the URL', st in (302, 303) and 'q=' not in (loc or '') and 'عل' not in (loc or ''), '%s %s' % (st, loc))
st, body = get(own, '/my/workspaces/%s/clients' % A)
check('Arabic ي finds the Persian name; others are filtered out', 'علیرضا کریمی' in tbl(body) and 'بدون کارشناس' not in tbl(body) and 'نتیجهٔ جست‌وجو' in body)
post(own, '/my/workspaces/%s/clients' % A, {'q': 'S-100', 'filter': 'all'})
check('search by the panel\'s own code', 'علیرضا کریمی' in tbl(get(own, '/my/workspaces/%s/clients' % A)[1]))
post(own, '/my/workspaces/%s/clients' % A, {'q': '', 'filter': 'all'})
check('clearing the search shows everything again', 'بدون کارشناس' in tbl(get(own, '/my/workspaces/%s/clients' % A)[1]))
check('search POST without CSRF is refused', own.req('/my/workspaces/%s/clients' % A, {'q': 'x'})[0] in (400, 403))

# filters
st, body = get(own, '/my/workspaces/%s/clients?filter=imported' % A)
check('filter «واردشده»', 'فرد تاریخی' in tbl(body) and 'علیرضا کریمی' not in tbl(body))
st, body = get(own, '/my/workspaces/%s/clients?filter=unassigned' % A)
check('filter «بدون کارشناس»', 'بدون کارشناس' in tbl(body) and 'علیرضا کریمی' not in tbl(body))
st, body = get(own, '/my/workspaces/%s/clients?filter=archived' % A)
check('filter «بایگانی‌شده»', 'بایگانی‌شده' in tbl(body) and 'علیرضا کریمی' not in tbl(body))

# counselors: own + unassigned only (education)
c1 = login('c1')
st, body = get(c1, '/my/workspaces/%s/clients' % A)
check('counselor 1 sees own and unassigned', st == 200 and 'علیرضا کریمی' in tbl(body) and 'بدون کارشناس' in tbl(body), str(st))
check('counselor 1 does not see a colleague\'s client', 'مریم از کارشناس دو' not in tbl(body))
st, body = get(c1, '/my/workspaces/%s/clients/%s' % (A, K2))
check('counselor 1 opening a colleague\'s client: 403 in the shell', st == 403 and 'tsp-nav' in body, str(st))
st, body = get(c1, '/my/workspaces/%s/clients/%s' % (A, K1))
check('counselor 1 opens own client', st == 200 and 'علیرضا کریمی' in body and 'name="responsible_id"' not in body, str(st))
st, _, _ = post(c1, '/my/workspaces/%s/clients/%s/responsible' % (A, K1), {'responsible_id': M2})
check('counselor cannot assign (403)', st == 403, str(st))

# hiring manager: own only
hm = login('hm')
st, body = get(hm, '/my/workspaces/%s/clients' % H)
check('hiring manager sees only own', st == 200 and 'متقاضی من' in body and 'متقاضی همکار' not in body, str(st))
check('foreign panel client id through my panel route is 404', get(hm, '/my/workspaces/%s/clients/%s' % (H, K1))[0] == 404)
check('a stranger gets 404 on the list and a client', get(login('outsider'), '/my/workspaces/%s/clients' % A)[0] == 404
      and get(login('outsider'), '/my/workspaces/%s/clients/%s' % (A, K1))[0] == 404)

# client page and responsible
st, body = get(own, '/my/workspaces/%s/clients/%s' % (A, K1))
check('owner sees the responsible form', st == 200 and 'name="responsible_id"' in body)
st, loc, _ = post(own, '/my/workspaces/%s/clients/%s/responsible' % (A, K1), {'responsible_id': M2})
st2, body = get(own, '/my/workspaces/%s/clients/%s' % (A, K1))
check('owner hands the client to the colleague', 'کارشناس مسئول ذخیره شد' in body, '%s %s' % (st, loc))
st, _, _ = post(own, '/my/workspaces/%s/clients/%s/responsible' % (A, K1), {'responsible_id': '999999'})
check('unknown member id is a 404', st == 404, str(st))
post(own, '/my/workspaces/%s/clients/%s/responsible' % (A, K1), {'responsible_id': M1})
st, body = get(own, '/my/workspaces/%s/clients/%s' % (A, KI))
check('imported client page says contact data is not kept', st == 200 and 'نمایش داده نمی‌شود' in body and 'واردشده' in body, str(st))
check('eot.ir has no clients page', (lambda e: (e.login(L['owner'], pw[L['owner']]), e.req('/my/workspaces/%s/clients' % A)[0])[1])(Client('www.eot.ir')) == 404)
summary()
