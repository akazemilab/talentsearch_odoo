#!/usr/bin/env python3
"""Panel v2 S18 (transfer ownership, close panel) over HTTP against a served CLONE:  ts_http_pv2_18.py DB PORT"""
import importlib.util, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
NAMES = ('owner', 'adm', 'cns', 'owner2', 'adm2')
L = {n: 'ts.pv2s18.%s.http@example.invalid' % n for n in NAMES}
pw = {u: ensure_user(u) for u in L.values()}

code = r"""
L = %r
def user(n): return env['res.users'].search([('login', '=', L[n])])
def panel(name, purpose):
    org = env['res.partner'].search([('name', '=', name)], limit=1) or env['res.partner'].create({'name': name, 'is_company': True})
    org.write({'is_company': True})
    ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create({'name': name, 'purpose': purpose, 'partner_id': org.id})
    ws.write({'approved_on': '2026-01-01 00:00:00'})
    if ws.state in ('draft', 'closed'):
        ws.write({'state': 'pilot', 'closed_on': False})
    return ws
def member(ws, n, role):
    u = user(n)
    m = env['ts.workspace.member'].search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)]) or env['ts.workspace.member'].create(
        {'workspace_id': ws.id, 'user_id': u.id, 'role': role})
    if m.role != role:
        m.write({'role': role})
    return m
T1 = panel('S18 http transfer', 'education'); T2 = panel('S18 http close', 'education')
mo, ma, mc = member(T1, 'owner', 'owner'), member(T1, 'adm', 'admin'), member(T1, 'cns', 'counselor')
mo2, ma2 = member(T2, 'owner2', 'owner'), member(T2, 'adm2', 'admin')
env.cr.commit()
print('IDS', T1.id, T2.id, ma.id, mo.id, mo2.id)
""" % L
out = shell(code)
mm = re.search(r'IDS (\d+) (\d+) (\d+) (\d+) (\d+)', out)
assert mm, out[-1500:]
T1, T2, MA, MO, MO2 = mm.groups()
W1, W2 = '/my/workspaces/%s' % T1, '/my/workspaces/%s' % T2


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


def q(sql):
    o = shell("cr = env.cr; cr.execute(%r); print('Q', cr.fetchall())" % sql)
    m = re.findall(r'^Q (.*)$', o, re.M)
    return m[-1] if m else o


ow, ad = login('owner'), login('adm')

# ---- who sees the lifecycle block
st, page = get(ow, W1 + '/settings')
check('the owner sees the lifecycle block', st == 200 and 'tsp-lifecycle' in page, st)
st, page = get(ad, W1 + '/settings')
check('an admin cannot open the settings page at all (403)', st == 403 and 'tsp-lifecycle' not in page, st)
st, _ = get(ad, W1 + '/settings/transfer')
check('an admin gets 403 on the transfer page', st == 403, st)
st, _ = get(ad, W1 + '/settings/close')
check('an admin gets 403 on the close page', st == 403, st)

# ---- transfer
st, page = get(ow, W1 + '/settings/transfer')
check('the owner sees the transfer page with the other members', st == 200 and 'name="new_owner"' in page and 'value="%s"' % MA in page, st)
check('the owner themself is not offered', 'value="%s"' % MO not in page)
st, loc, _ = post(ow, W1 + '/settings/transfer', {'new_owner': MA, 'stay': 'admin'})
check('a transfer asks for re-authentication', st in (302, 303) and '/my/reauth' in (loc or ''), '%s %s' % (st, loc))
check('nothing changed before re-authentication', "('owner',)" in q("select role from ts_workspace_member where id=%s" % MO))
post(ow, '/my/reauth/verify', {'password': pw[L['owner']], 'next': W1 + '/settings/transfer'})
st, loc, _ = post(ow, W1 + '/settings/transfer', {'new_owner': MA, 'stay': 'admin'})
check('after re-authentication the transfer succeeds', st in (302, 303) and '/settings' in (loc or '') and 'reauth' not in (loc or ''), '%s %s' % (st, loc))
check('the new owner holds the role and the old owner is admin',
      "('owner',)" in q("select role from ts_workspace_member where id=%s" % MA) and "('admin',)" in q("select role from ts_workspace_member where id=%s" % MO))
st, page = get(ad, W1 + '/settings')
check('the new owner now sees the lifecycle block', st == 200 and 'tsp-lifecycle' in page)
st, page = get(ow, W1 + '/settings')
check('the old owner (now admin) no longer gets the page', st == 403 and 'tsp-lifecycle' not in page, st)
st, loc, _ = post(ad, W2 + '/settings/transfer', {'new_owner': MA})
check('a non-member of the other panel is refused (404)', st in (403, 404), st)

# ---- close
o2 = login('owner2')
st, page = get(o2, W2 + '/settings/close')
check('the close page names the panel and what happens', st == 200 and 'S18 http close' in page and '۹۰' in page, st)
st, loc, _ = post(o2, W2 + '/settings/close', {})
check('closing without the tick is refused', 'close' in (loc or '') and 'reauth' not in (loc or ''), loc)
st, loc, _ = post(o2, W2 + '/settings/close', {'confirm': '1'})
check('closing asks for re-authentication', st in (302, 303) and '/my/reauth' in (loc or ''), '%s %s' % (st, loc))
post(o2, '/my/reauth/verify', {'password': pw[L['owner2']], 'next': W2 + '/settings/close'})
st, loc, _ = post(o2, W2 + '/settings/close', {'confirm': '1'})
check('after re-authentication the panel closes', st in (302, 303) and 'reauth' not in (loc or ''), '%s %s' % (st, loc))
check('the panel row is closed with a time', "('closed', True)" in q("select state, closed_on is not null from ts_workspace where id=%s" % T2))
st, page = get(o2, W2)
check('the closed panel shows the closed notice', st == 200, st)
a2 = login('adm2')
st, _ = get(a2, W2 + '/clients')
check('staff lose the clients page of a closed panel', st in (403, 404), st)

summary()
