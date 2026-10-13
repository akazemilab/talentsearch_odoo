#!/usr/bin/env python3
"""Panel v2 S18b (sessions page, idle timeout, SMS risk notice) over HTTP against a served CLONE:  ts_http_pv2_18b.py DB PORT"""
import importlib.util, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
lib.fake_kavenegar()     # the mobile sign-in (S-AUTH) needs an SMS gateway: a local fake, never a live route
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
NAMES = ('staff', 'part')
L = {n: 'ts.pv2s18b.%s.http@example.invalid' % n for n in NAMES}
pw = {u: ensure_user(u) for u in L.values()}

code = r"""
L = %r
def user(n): return env['res.users'].search([('login', '=', L[n])])
org = env['res.partner'].search([('name', '=', 'S18b http')], limit=1) or env['res.partner'].create({'name': 'S18b http', 'is_company': True})
org.write({'is_company': True})
ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create({'name': 'S18b http', 'purpose': 'education', 'partner_id': org.id})
if ws.state in ('draft', 'closed'):
    ws.write({'state': 'active'})
u = user('staff')
env['ts.workspace.member'].search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)]) or env['ts.workspace.member'].create(
    {'workspace_id': ws.id, 'user_id': u.id, 'role': 'owner'})
env['ir.config_parameter'].sudo().set_float('ts_panel.staff_idle_hours', 8.0)
# sessions left by an earlier run would hide a missing one: start every run from none
env['res.session'].sudo().search([('user_id', '=', u.id), ('revoked', '=', False)])._revoke()
env.cr.commit()
print('OK seeded')
""" % L
_o = shell(code)
assert 'OK seeded' in _o, 'seed failed: ' + _o[-1200:]


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


a, b = login('staff'), login('staff')
get(b, '/my')   # the second device makes one request, so its session is recorded like a real one
st, page = get(a, '/my/sessions')
# since the UX audit the «others» form shows only with 2+ sessions and the current row has no form: every name="sid"
# is another device (or the «others» form), so >= 2 means the other session row and the «others» form are both there
check('the sessions page opens and lists at least two sessions', st == 200 and page.count('name="sid"') >= 2
      and 'id="ses-others"' in page, st)
check('the current session is marked and not revocable', 'ts-sess-current' in page, st)

st, loc, _ = post(a, '/my/sessions/revoke', {'sid': 'others'})
check('revoking other sessions asks for re-authentication', st in (302, 303) and '/my/reauth' in (loc or ''), '%s %s' % (st, loc))
st, _ = get(b, '/my/sessions')
check('nothing was revoked before re-authentication', st == 200, st)
post(a, '/my/reauth/verify', {'password': pw[L['staff']], 'next': '/my/sessions'})
st, loc, _ = post(a, '/my/sessions/revoke', {'sid': 'others'})
check('after re-authentication the others are revoked', st in (302, 303) and 'reauth' not in (loc or ''), '%s %s' % (st, loc))
st, loc, _ = b.req('/my/sessions')
check('the other client is sent to sign in', st in (302, 303) and 'login' in (loc or ''), '%s %s' % (st, loc))
st, _ = get(a, '/my/sessions')
check('the acting client stays signed in', st == 200, st)

# ---- idle timeout (tiny value, short sleep)
shell("env['ir.config_parameter'].sudo().set_float('ts_panel.staff_idle_hours', 0.0006); env.cr.commit()")
c = login('staff')
st, _ = get(c, '/my/sessions')
check('a fresh staff session works under the timeout', st == 200, st)
time.sleep(4)
st, loc, _ = c.req('/my/sessions')
check('an idle staff session is signed out', st in (302, 303) and 'login' in (loc or ''), '%s %s' % (st, loc))

# a participant (not a panel member) is not subject to the timeout
c = login('part')
get(c, '/my')
time.sleep(4)
st, loc, _ = c.req('/my')
check('a person who is no panel member keeps the session', st == 200 or (st in (302, 303) and 'login' not in (loc or '')), '%s %s' % (st, loc))
shell("env['ir.config_parameter'].sudo().set_float('ts_panel.staff_idle_hours', 8.0); env.cr.commit()")

# ---- the e-mail way stays reachable from the mobile sign-in (onb1)
st, body = get(Client(TS), '/signup')
check('the sign-in page offers the e-mail way quietly', st == 200 and 'با ایمیل ثبت‌نام کرده بودید؟' in body and '/web/login?email=1' in body, st)

summary()
