#!/usr/bin/env python3
"""Panel v2 S11 (credits page) over HTTP against a served CLONE:  ts_http_pv2_11.py DB PORT"""
import importlib.util, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
NAMES = ('owner', 'c1', 'hr', 'rv', 'other')
L = {n: 'ts.pv2s11.%s.http@example.invalid' % n for n in NAMES}
pw = {u: ensure_user(u) for u in L.values()}

code = r"""
L = %r
import json
from odoo import fields
def user(n): return env['res.users'].search([('login', '=', L[n])])
def panel(name, purpose):
    org = env['res.partner'].search([('name', '=', name)], limit=1) or env['res.partner'].create({'name': name, 'is_company': True})
    org.write({'is_company': True})
    ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create({'name': name, 'purpose': purpose, 'partner_id': org.id})
    ws.write({'approved_on': '2026-01-01 00:00:00'}); ws.state = 'pilot'
    return ws
def member(ws, n, role):
    u = user(n)
    m = env['ts.workspace.member'].search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)]) or env['ts.workspace.member'].create(
        {'workspace_id': ws.id, 'user_id': u.id, 'role': role})
    if role == 'counselor':
        m.write({'license_number': 'T-1', 'verification_state': 'verified'})
    return m
A = panel('پنل S11 آموزشی', 'education'); B = panel('پنل S11 کاری', 'employment')
member(A, 'owner', 'owner'); member(A, 'c1', 'counselor'); member(B, 'hr', 'hr_admin'); member(B, 'rv', 'reviewer'); member(B, 'other', 'owner')
talent = env['ts.instrument'].search([('code', '=', 'TALENT-INV-15')], limit=1)
portal = env.ref('base.group_portal')
def puser(i):
    login = 'ts.pv2s11.part%%d.http@example.invalid' %% i
    return env['res.users'].search([('login', '=', login)]) or env['res.users'].with_context(no_reset_password=True).create(
        {'name': 'p%%d' %% i, 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})
Asg = env['ts.assignment']
for nm, i in (('دانش‌آموز اعتبار یک', 1), ('دانش‌آموز اعتبار دو', 2)):
    if not Asg.search_count([('workspace_id', '=', A.id), ('invitee_name', '=', nm)]):
        a = Asg.create({'workspace_id': A.id, 'instrument_id': talent.id, 'invitee_name': nm})
        at = a.action_accept(puser(i), share=True)
        at.write({'state': 'done', 'released': True, 'submitted_at': fields.Datetime.now()})
        at._ts_panel_record_usage()
if not Asg.search_count([('workspace_id', '=', A.id), ('invitee_name', '=', 'دعوت باز اعتبار')]):
    Asg.create({'workspace_id': A.id, 'instrument_id': talent.id, 'invitee_name': 'دعوت باز اعتبار'})
env['ts.wallet']._for_workspace(B)
env.cr.commit()
w = env['ts.wallet']._for_workspace(A)
print('IDS', A.id, B.id, w.units_used, w.committed())
""" % L
out = shell(code)
mm = re.search(r'IDS (\d+) (\d+) (\d+) (\d+)', out)
assert mm, out[-1500:]
A, B = mm.group(1), mm.group(2)
used, committed = int(mm.group(3)), int(mm.group(4))
WA, WB = '/my/workspaces/%s' % A, '/my/workspaces/%s' % B


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


own, c1, hr, rv, oth = login('owner'), login('c1'), login('hr'), login('rv'), login('other')

st, body = get(own, WA + '/credits')
check('the credits page opens with one h1 and its sections', st == 200 and body.count('<h1') == 1 and 'اعتبار و مصرف' in body and 'تاریخچه' in body, str(st))
check('free mode: the banner says «رایگان در این فصل»', 'رایگان در این فصل' in body)
check('the page never shows a price or currency', not any(w in body for w in ('ریال', 'تومان', 'قیمت', 'پرداخت')))
check('the tiles show the total usage and the open invitations', ('>%s<' % str(used).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))) in body and used >= 2 and committed >= 1)
check('the balance tile is hidden while free', 'موجودی' not in body)
check('the history lists the panel\'s own rows', body.count('<tr') >= 1 + used)
check('the menu has the credits item', WA + '/credits' in get(own, WA)[1])
check('a counselor gets the 403 page', get(c1, WA + '/credits')[0] == 403)
st, body = get(hr, WB + '/credits')
check('the hr admin of an employment panel may read credits', st == 200 and 'رایگان در این فصل' in body)
check('...and sees none of the other panel\'s rows', 'دانش‌آموز' not in body)
check('a reviewer gets the 403 page', get(rv, WB + '/credits')[0] == 403)
check('a member of another panel gets 404', get(oth, WA + '/credits')[0] == 404)
check('an anonymous visitor is sent to sign in', Client(TS).req(WA + '/credits')[0] in (302, 303))
e = Client('www.eot.ir')
e.login(L['owner'], pw[L['owner']])
check('eot.ir does not serve the credits page', e.req(WA + '/credits')[0] == 404)
check('the credits route is read only', own.req(WA + '/credits', [('x', '1')])[0] in (400, 403, 404, 405))
summary()
