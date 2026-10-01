#!/usr/bin/env python3
"""Panel v2 S12 (dashboard) over HTTP against a served CLONE:  ts_http_pv2_12.py DB PORT
Every number on the dashboard must equal the count on the list its link opens."""
import importlib.util, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
NAMES = ('owner', 'c1', 'c2')
L = {n: 'ts.pv2s12.%s.http@example.invalid' % n for n in NAMES}
pw = {u: ensure_user(u) for u in L.values()}
LATIN = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')

code = r"""
L = %r
from datetime import timedelta
from odoo import fields
def user(n): return env['res.users'].search([('login', '=', L[n])])
org = env['res.partner'].search([('name', '=', 'پنل S12 وب')], limit=1) or env['res.partner'].create({'name': 'پنل S12 وب', 'is_company': True})
org.write({'is_company': True})
ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create({'name': 'پنل S12 وب', 'purpose': 'education', 'partner_id': org.id})
ws.write({'approved_on': '2026-01-01 00:00:00', 'onboarding_dismissed_on': False}); ws.state = 'pilot'
mem = {}
for n, role in (('owner', 'owner'), ('c1', 'counselor'), ('c2', 'counselor')):
    m = env['ts.workspace.member'].search([('workspace_id', '=', ws.id), ('user_id', '=', user(n).id)]) or env['ts.workspace.member'].create(
        {'workspace_id': ws.id, 'user_id': user(n).id, 'role': role})
    if role == 'counselor':
        m.write({'license_number': 'T-1', 'verification_state': 'verified'})
    mem[n] = m
C, A = env['ts.panel.client'], env['ts.assignment']
talent = env['ts.instrument'].search([('code', '=', 'TALENT-INV-15')], limit=1)
portal = env.ref('base.group_portal')
def puser(i):
    login = 'ts.pv2s12.part%%d.http@example.invalid' %% i
    return env['res.users'].search([('login', '=', login)]) or env['res.users'].with_context(no_reset_password=True).create(
        {'name': 'p%%d' %% i, 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})
def client(name, resp=None):
    return C.search([('workspace_id', '=', ws.id), ('name', '=', name)], limit=1) or C.create({'workspace_id': ws.id, 'name': name, 'responsible_id': resp.id if resp else False})
if not A.search_count([('workspace_id', '=', ws.id)]):
    client('بدون مسئول ۱'); client('بدون مسئول ۲')
    k3 = client('مراجع یک', mem['c1']); k4 = client('مراجع دو', mem['c2'])
    k3.write({'handover_to_id': mem['c2'].id, 'handover_by_id': mem['c1'].id, 'handover_on': fields.Datetime.now()})
    today = fields.Date.today()
    o = A.create({'workspace_id': ws.id, 'instrument_id': talent.id, 'client_id': k3.id, 'invitee_name': k3.name})
    env.cr.execute("UPDATE ts_assignment SET deadline = %%s WHERE id = %%s", [today - timedelta(days=3), o.id])
    e = A.create({'workspace_id': ws.id, 'instrument_id': talent.id, 'client_id': k4.id, 'invitee_name': k4.name})
    env.cr.execute("UPDATE ts_assignment SET expires_at = now() at time zone 'utc' + interval '1 day' WHERE id = %%s", [e.id])
    for i in range(6):
        k = client('تکمیل‌شده %%d' %% i, mem['c1'] if i %% 2 else mem['c2'])
        a = A.create({'workspace_id': ws.id, 'instrument_id': talent.id, 'client_id': k.id, 'invitee_name': k.name})
        at = a.action_accept(puser(i + 1), share=bool(i %% 2))
        at.write({'state': 'done', 'released': True, 'started_at': fields.Datetime.now() - timedelta(minutes=9 + i), 'submitted_at': fields.Datetime.now()})
env.cr.commit()
print('WS', ws.id)
""" % L
out = shell(code)
mm = re.search(r'WS (\d+)', out)
assert mm, out[-1500:]
WS = mm.group(1)
W = '/my/workspaces/%s' % WS


def login(n):
    c = Client(TS)
    assert c.login(L[n], pw[L[n]]), n
    return c


def get(c, path):
    for _ in range(4):
        st, loc, body = c.req(path)
        if st in (301, 302, 303) and loc:
            path = path_of(loc)
            continue
        break
    return st, body


def post(c, path, data=None):
    pairs = list((data or {}).items())
    pairs.append(('csrf_token', c.csrf(c.req('/web/login')[2])))
    return c.req(path, pairs)


def num(s):
    return int(re.sub(r'\D', '', s.translate(LATIN)) or 0)


def list_count(c, url):
    st, body = get(c, url)
    if '/clients' in url:
        m = re.search(r'([0-9۰-۹]+) مورد ·', body)
    else:
        m = re.search(r'\(<span class="ts-num">([0-9۰-۹]+)</span> دعوت\)', body)
    return st, (num(m.group(1)) if m else 0)          # an empty list shows no count line


own, c1, c2 = login('owner'), login('c1'), login('c2')

# ---- structure
st, body = get(own, W)
check('the dashboard opens with one h1', st == 200 and body.count('<h1') == 1, str(st))
check('needs-attention comes before the period summary', 0 <= body.find('id="tsp-d-att"') < body.find('id="tsp-d-kpi"'))
check('the period chips mark the current one', 'aria-current="true"' in body and '?period=7' in body and '?period=90' in body)
check('an unknown period falls back to 30 days', get(own, W + '?period=5')[1].count('aria-current="true"') == get(own, W)[1].count('aria-current="true"'))
check('no score or band appears', 'نمره' not in body and 'سطح زیاد' not in body)
check('eot.ir does not serve it', (lambda e: (e.login(L['owner'], pw[L['owner']]), e.req(W)[0])[1])(Client('www.eot.ir')) == 404)

# ---- every number equals the list behind it
pat = re.compile(r'<a[^>]*href="(/my/workspaces/%s/(?:invites|clients)\?[^"]*)"[^>]*>\s*<strong class="ts-num">([^<]*)</strong>' % WS)
links = [(u.replace('&amp;', '&'), t) for u, t in pat.findall(body)]
bad = []
for u, t in links:
    exp = num(t.split('از')[-1]) if 'از' in t else num(t)
    st, got = list_count(own, u)
    if st != 200 or got != exp:
        bad.append((u, exp, got))
check('at least five tiles or lines link to a list', len(links) >= 5, str(len(links)))
check('every dashboard number equals the count on its list', not bad, str(bad))
fun = re.findall(r'<th scope="row"><a href="([^"]+)">[^<]*</a></th>\s*<td class="ts-num">([^<]*)</td>', body)
badf = []
for u, t in fun:
    st, got = list_count(own, u.replace('&amp;', '&'))
    if st != 200 or got != num(t):
        badf.append((u, num(t), got))
check('the funnel has five rows and each count equals its list', len(fun) == 5 and not badf, str(badf))
check('the funnel data table has a caption', 'مسیر دعوت‌ها' in body and '<caption' in body)

# ---- filtered list: the notice and the way out
st, body2 = get(own, W + '/invites?overdue=1')
check('a filtered invitation list says what it shows and offers «نمایش همه»', st == 200 and 'نمایش فقط' in body2 and 'نمایش همه' in body2)
check('an unknown filter value is ignored', 'نمایش فقط' not in get(own, W + '/invites?kind=zzz&overdue=2')[1])
st, b3 = get(own, W + '/clients?filter=handover')
check('the client list has the handover filter', st == 200 and 'درخواست واگذاری' in b3)

# ---- roles
st, cb = get(c1, W)
check('a counselor sees the dashboard without workload and credits', st == 200 and 'حجم کار اعضا' not in cb and 'مصرف این دوره' not in cb)
check('...and without the setup checklist', 'گام‌های راه‌اندازی' not in cb)
cl = [(u.replace('&amp;', '&'), t) for u, t in pat.findall(cb)]
badc = [(u, t) for u, t in cl if list_count(c1, u)[1] != (num(t.split('از')[-1]) if 'از' in t else num(t))]
check('a counselor\'s numbers equal their own lists', cl and not badc, str(badc))
check('the owner sees the workload and credits tile', 'حجم کار اعضا' in body and 'مصرف این دوره' in body and 'رایگان در این فصل' in body)

# ---- checklist and dismissal
check('the owner sees the checklist', 'گام‌های راه‌اندازی' in body)
check('a counselor cannot dismiss it', post(c1, W + '/dashboard/dismiss')[0] == 403)
st, loc, _ = post(own, W + '/dashboard/dismiss')
check('the owner can dismiss it', st in (302, 303) and 'گام‌های راه‌اندازی' not in get(own, W)[1])
check('dismiss needs a CSRF token', own.req(W + '/dashboard/dismiss', [('x', '1')])[0] in (400, 403))
shell("ws = env['ts.workspace'].browse(%s); ws.onboarding_dismissed_on = False; env.cr.commit()" % WS)
summary()
