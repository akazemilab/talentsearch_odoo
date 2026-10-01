#!/usr/bin/env python3
"""Panel v2 S1 over HTTP against a served CLONE:  ts_http_pv2_1.py DB PORT
Deny cases first: a stranger gets 404 and a throttled deny event (P24); the coordinator (admin) sees the
panel without the members and settings sections; POSTs are refused; a solo psychologist keeps owner_practices."""
import importlib.util, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell
TS = 'talentsearch.ir'
OWN, ADM, CNS, OUT, SOLO = ('ts.pv2s1.%s.http@example.invalid' % n for n in ('owner', 'admin', 'counselor', 'outsider', 'solo'))
pw = {u: ensure_user(u) for u in (OWN, ADM, CNS, OUT, SOLO)}
code = r'''
org = env['res.partner'].search([('name', '=', 'پنل S1 HTTP')], limit=1) or env['res.partner'].create({'name': 'پنل S1 HTTP', 'is_company': True})
ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create({'name': 'پنل S1 HTTP', 'purpose': 'education', 'partner_id': org.id})
ws.write({'approved_on': '2026-01-01 00:00:00'}); ws.state = 'pilot'
M = env['ts.workspace.member']
for login, role in ((OWN, 'owner'), (ADM, 'admin'), (CNS, 'counselor')):
    u = env['res.users'].search([('login', '=', login)])
    m = M.search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)])
    if not m:
        M.create({'workspace_id': ws.id, 'user_id': u.id, 'role': role})
    elif m.role != role:
        m.role = role
    if role == 'counselor':
        M.search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)]).write({'license_number': 'T-1', 'verification_state': 'verified'})
env.cr.commit()
print('WS', ws.id)
'''.replace('OWN', repr(OWN)).replace('ADM', repr(ADM)).replace('CNS', repr(CNS))
out = shell(code)
mm = re.search(r'WS (\d+)', out)
assert mm, out[-1500:]
ws_id = mm.group(1)


def denies():
    o = shell("print('N', env['ts.audit.event'].search_count([('event_type','=','authz.deny'),('workspace_id','=',%s)]))" % ws_id)
    return int(re.search(r'N (\d+)', o).group(1))


# ---- a stranger
x = Client(TS)
check('stranger login', x.login(OUT, pw[OUT]))
n0 = denies()
st, _, _ = x.req('/my/workspaces/%s' % ws_id)
check('stranger gets 404 for a panel of others', st == 404, str(st))
n1 = denies()
check('P24 the deny event survived the 404 (own cursor)', n1 == n0 + 1, '%s -> %s' % (n0, n1))
for _ in range(3):
    x.req('/my/workspaces/%s' % ws_id)
check('P24 repeated denials within a minute are throttled to one row', denies() == n1, str(denies()))
d = shell("r = env['ts.audit.event'].search([('event_type','=','authz.deny'),('workspace_id','=',%s)], limit=1)\nprint('ROW', r.outcome, r.route, bool(r.ip_hash), r.ip_address or '-')" % ws_id)
check('P24 deny row has outcome, id-free route and a hashed address, no raw IP',
      'ROW denied /my/workspaces/<id> True -' in d, d[-200:])
st, _, _ = x.req('/my/workspaces/%s/settings' % ws_id, {'name': 'x', 'csrf_token': 'bad'})
check('POST with a bad CSRF token is refused', st in (400, 403), str(st))

# ---- the coordinator (admin)
a = Client(TS)
check('admin login', a.login(ADM, pw[ADM]))
st, _, page = a.req('/my/workspaces/%s' % ws_id)
check('admin opens the panel page', st == 200 and 'Traceback' not in page, str(st))
check('admin does not get the members or settings sections', 'id="ts-members"' not in page and 'id="ts-settings"' not in page)
csrf = a.csrf(page)
st, _, _ = a.req('/my/workspaces/%s/settings' % ws_id, {'name': 'نام تازه', 'csrf_token': csrf})
check('admin settings POST is refused (404)', st == 404, str(st))
st, _, _ = a.req('/my/workspaces/%s/members/invite' % ws_id, {'role': 'counselor', 'email': 'zzz@example.invalid', 'csrf_token': csrf})
n_inv = shell("print('N', env['ts.member.invite'].sudo().search_count([('workspace_id','=',%s),('email','=','zzz@example.invalid')]))" % ws_id)
check('admin cannot invite colleagues', st in (302, 303, 404) and 'N 0' in n_inv, '%s %s' % (st, n_inv.strip()[-20:]))

# ---- counselor and owner
c = Client(TS)
check('counselor login', c.login(CNS, pw[CNS]))
st, _, page = c.req('/my/workspaces/%s' % ws_id)
check('counselor opens the panel without members and settings', st == 200 and 'id="ts-members"' not in page and 'id="ts-settings"' not in page)
o = Client(TS)
check('owner login', o.login(OWN, pw[OWN]))
st, _, page = o.req('/my/workspaces/%s' % ws_id)
check('owner sees the members and settings sections', st == 200 and 'id="ts-members"' in page and 'id="ts-settings"' in page and 'Traceback' not in page)
check('owner role label is «مالک پنل»', 'مالک پنل' in page)

# ---- solo psychologist: owner_practices and the licence number
s = Client(TS)
check('solo login', s.login(SOLO, pw[SOLO]))
st, _, form = s.req('/my/workspaces/new')
check('create form has the licence field', st == 200 and 'name="license_number"' in form, str(st))
st, loc, _ = s.req('/my/workspaces/new/create', {
    'name': 'روان‌شناس S1 HTTP %s' % os.getpid(), 'kind': 'solo', 'solo_as': 'psychologist', 'license_number': 'PSY-123',
    'terms': '1', 'escalation_ok': '1', 'csrf_token': s.csrf(form)})
check('solo clinical panel is created', st in (302, 303) and 'new=1' in (loc or ''), '%s %s' % (st, loc))
r = shell("m = env['ts.workspace.member'].search([('user_id.login','=',%r),('role','=','owner')], order='id desc', limit=1)\n"
          "print('SOLO', m.owner_practices, m.license_number, m.workspace_id.purpose)" % SOLO)
check('the solo owner practises and keeps the licence number', 'SOLO True PSY-123 clinical' in r, r[-120:])
summary()
