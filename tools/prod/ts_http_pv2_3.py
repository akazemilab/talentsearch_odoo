#!/usr/bin/env python3
"""Panel v2 S3 (members + re-authentication) over HTTP against a served CLONE:  ts_http_pv2_3.py DB PORT
No real SMS: the test users have no verified mobile, so re-authentication uses the password path."""
import importlib.util, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell
TS = 'talentsearch.ir'
NAMES = ('owner', 'admin', 'counselor', 'hm', 'target', 'outsider')
L = {n: 'ts.pv2s3.%s.http@example.invalid' % n for n in NAMES}
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
A = panel('پنل S3 آموزشی', 'education')
member(A, 'owner', 'owner'); member(A, 'admin', 'admin'); member(A, 'counselor', 'counselor'); t = member(A, 'target', 'counselor')
H = panel('پنل S3 استخدامی', 'employment'); member(H, 'hm', 'hiring_manager'); member(H, 'owner', 'owner')
env.cr.commit()
print('IDS', A.id, H.id, t.id)
''' % L
out = shell(code)
mm = re.search(r'IDS (\d+) (\d+) (\d+)', out)
assert mm, out[-1500:]
A, H, T = mm.groups()


def login(n):
    c = Client(TS)
    assert c.login(L[n], pw[L[n]]), n
    return c


def page(c, path):
    st, loc, body = c.req(path)
    return st, body


def post(c, path, data, src=None):
    tok = c.csrf(c.req(src or '/my/workspaces/new')[2])
    d = dict(data); d['csrf_token'] = tok
    return c.req(path, d)


own = login('owner')
st, body = page(own, '/my/workspaces/%s/members' % A)
check('owner opens the member list', st == 200 and 'اعضا و نقش‌ها' in body and body.count('<h1') == 1, str(st))
check('the list is a real table with scope headers', 'scope="col"' in body)
for n in ('admin', 'counselor'):
    st, body = page(login(n), '/my/workspaces/%s/members' % A) if n == 'admin' else (0, '')
check('admin may read the member list', st == 200)
st, body = page(login('counselor'), '/my/workspaces/%s/members' % A)
check('counselor gets the 403 page in the shell', st == 403 and 'به این بخش دسترسی ندارید' in body, str(st))
st, body = page(login('hm'), '/my/workspaces/%s/members' % H)
check('hiring manager gets the 403 page', st == 403, str(st))
check('a stranger gets 404', page(login('outsider'), '/my/workspaces/%s/members' % A)[0] == 404)
st, body = page(login('admin'), '/my/workspaces/%s/members' % A)
check('admin sees no role-change controls', 'name="role"' not in body or '/role' not in body)

# invite, resend, revoke
st, loc, _ = post(own, '/my/workspaces/%s/members/add' % A, {'role': 'counselor', 'phone': '09121119999'}, '/my/workspaces/%s/members' % A)
check('invite redirects to the list with the new link', st in (302, 303) and 'minv=' in (loc or ''), '%s %s' % (st, loc))
st, body = page(own, loc.split(TS)[-1] if loc and TS in loc else loc)
check('the new link is shown once, with a copy-friendly field', '/join/' in body, str(st))
inv_id = re.search(r'minv=(\d+)', loc).group(1)
tok1 = re.search(r'/join/([A-Za-z0-9_\-]+)', body).group(1)
st, loc2, _ = post(own, '/my/workspaces/%s/members/invites/%s/resend' % (A, inv_id), {}, '/my/workspaces/%s/members' % A)
check('send again redirects to the new invite', st in (302, 303) and 'minv=' in (loc2 or ''), '%s %s' % (st, loc2))
st, body = page(own, loc2.split(TS)[-1] if TS in loc2 else loc2)
tok2 = re.search(r'/join/([A-Za-z0-9_\-]+)', body).group(1)
check('the new token differs', tok1 != tok2)
stx, _, bx = Client(TS).req('/join/' + tok1)
check('the old link no longer works', 'Traceback' not in bx and ('دیگر معتبر نیست' in bx or stx in (404, 410)), str(stx))
new_id = re.search(r'minv=(\d+)', loc2).group(1)
st, _, _ = post(own, '/my/workspaces/%s/members/invites/%s/revoke' % (A, new_id), {}, '/my/workspaces/%s/members' % A)
check('revoke redirects', st in (302, 303), str(st))
stx, _, bx = Client(TS).req('/join/' + tok2)
check('the revoked link no longer works', 'دیگر معتبر نیست' in bx or stx in (404, 410), str(stx))
adm = login('admin')
st, _, _ = post(adm, '/my/workspaces/%s/members/add' % A, {'role': 'counselor', 'phone': '09121118888'}, '/my/workspaces/%s/members' % A)
check('admin may invite a counselor', st in (302, 303), str(st))
st, _, _ = post(adm, '/my/workspaces/%s/members/add' % A, {'role': 'owner', 'phone': '09121117777'}, '/my/workspaces/%s/members' % A)
check('admin cannot invite an owner (403)', st == 403, str(st))

# owner role needs fresh re-authentication
st, loc3, _ = post(own, '/my/workspaces/%s/members/add' % A, {'role': 'owner', 'phone': '09121116666'}, '/my/workspaces/%s/members' % A)
check('adding an owner without fresh re-auth redirects to /my/reauth', st in (302, 303) and '/my/reauth' in (loc3 or ''), '%s %s' % (st, loc3))
st, body = page(own, '/my/reauth?next=/my/workspaces/%s/members' % A)
check('reauth page (password path): one password field, no code field', st == 200 and 'type="password"' in body and 'name="code"' not in body)
st, loc4, _ = post(own, '/my/reauth/verify', {'password': 'wrong-pass', 'next': '/my/workspaces/%s/members' % A}, '/my/reauth')
st2, body = page(own, '/my/reauth?next=/my/workspaces/%s/members' % A)
check('a wrong password is refused with a message', 'رمز عبور درست نیست' in body and 'role="alert"' in body)
st, loc5, _ = post(own, '/my/reauth/verify', {'password': pw[L['owner']], 'next': '/my/workspaces/%s/members' % A}, '/my/reauth')
check('the right password goes back to the list', st in (302, 303) and (loc5 or '').endswith('/members'), '%s %s' % (st, loc5))
st, loc6, _ = post(own, '/my/workspaces/%s/members/add' % A, {'role': 'owner', 'phone': '09121116666'}, '/my/workspaces/%s/members' % A)
check('now the owner invite goes through', st in (302, 303) and 'minv=' in (loc6 or ''), '%s %s' % (st, loc6))
st, _, _ = post(own, '/my/reauth/verify', {'password': 'x', 'next': 'https://evil.example/'}, '/my/reauth')
check('open redirect is not possible', 'evil.example' not in (_ or ''))

# one member: role, deactivate, reactivate
st, body = page(own, '/my/workspaces/%s/members/%s' % (A, T))
check('member page opens for the owner', st == 200 and 'name="role"' in body, str(st))
st, loc7, _ = post(own, '/my/workspaces/%s/members/%s/role' % (A, T), {'role': 'admin'}, '/my/workspaces/%s/members/%s' % (A, T))
st, body = page(own, '/my/workspaces/%s/members/%s' % (A, T))
check('role changed and said so', 'نقش تغییر کرد' in body, str(st))
st, body = page(own, '/my/workspaces/%s/members/%s/deactivate' % (A, T))
check('deactivation asks for confirmation first', st == 200 and 'method="post"' in body.lower())
member_state = shell("print('ACT', env['ts.workspace.member'].browse(%s).active)" % T)
check('and nothing changed on GET', 'ACT True' in member_state)
st, _, _ = post(own, '/my/workspaces/%s/members/%s/deactivate' % (A, T), {}, '/my/workspaces/%s/members' % A)
member_state = shell("print('ACT', env['ts.workspace.member'].browse(%s).active)" % T)
check('POST deactivates', 'ACT False' in member_state)
st, body = page(own, '/my/workspaces/%s/members' % A)
check('inactive members stay in the list, labelled', 'غیرفعال' in body)
post(own, '/my/workspaces/%s/members/%s/reactivate' % (A, T), {}, '/my/workspaces/%s/members' % A)
member_state = shell("print('ACT', env['ts.workspace.member'].browse(%s).active)" % T)
check('reactivated', 'ACT True' in member_state)
st, _, _ = post(adm, '/my/workspaces/%s/members/%s/role' % (A, T), {'role': 'admin'}, '/my/workspaces/%s/members' % A)
check('admin cannot change a role (403)', st == 403, str(st))
st, _, _ = post(adm, '/my/workspaces/%s/members/%s/deactivate' % (A, T), {}, '/my/workspaces/%s/members' % A)
check('admin cannot deactivate (403)', st == 403, str(st))
check('POST without CSRF is refused', own.req('/my/workspaces/%s/members/add' % A, {'role': 'counselor', 'phone': '09121115555'})[0] in (400, 403))

# role help
st, body = page(own, '/help/roles')
labels_ok = all(w in body for w in ('مالک', 'مدیر', 'مشاور'))
check('role help lists the roles and a table with caption', st == 200 and labels_ok and '<caption' in body, str(st))
check('role help has no raw permission strings', 'members:' not in body and 'clients:' not in body)

# eot.ir has none of it
e = Client('www.eot.ir'); e.login(L['owner'], pw[L['owner']])
check('eot.ir has no members page', e.req('/my/workspaces/%s/members' % A)[0] == 404 and e.req('/my/reauth')[0] == 404)
summary()
