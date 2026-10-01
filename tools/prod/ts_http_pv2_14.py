#!/usr/bin/env python3
"""Panel v2 S14 (audit page, export, support access listing) over HTTP against a served CLONE:  ts_http_pv2_14.py DB PORT"""
import importlib.util, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
NAMES = ('owner', 'c1', 'other')
L = {n: 'ts.pv2s14.%s.http@example.invalid' % n for n in NAMES}
pw = {u: ensure_user(u) for u in L.values()}

code = r"""
L = %r
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
A = panel('پنل S14 آموزشی', 'education'); B = panel('پنل S14 دیگر', 'employment')
mo = member(A, 'owner', 'owner'); mc = member(A, 'c1', 'counselor'); mb = member(B, 'other', 'owner')
Ev = env['ts.audit.event'].sudo()
if not Ev.search_count([('workspace_id', '=', A.id), ('event_type', '=', 'member.add'), ('actor_id', '=', mc.user_id.id)]):
    Ev.with_user(mc.user_id).log('member.add', A, workspace=A, member=mc)
if not Ev.search_count([('workspace_id', '=', B.id), ('event_type', '=', 'export.create'), ('actor_id', '=', mb.user_id.id)]):
    Ev.with_user(mb.user_id).log('export.create', B, workspace=B, member=mb, secretmark=1)
mgr = env['res.users'].search([('login', '=', 'ts.pv2s14.mgr.http@example.invalid')]) or env['res.users'].with_context(no_reset_password=True).create(
    {'name': 'مدیر S14 http', 'login': 'ts.pv2s14.mgr.http@example.invalid', 'email': 'ts.pv2s14.mgr.http@example.invalid',
     'group_ids': [(6, 0, [env.ref('base.group_user').id, env.ref('ts_core.group_ts_manager').id])]})
if not env['ts.emergency.access'].search_count([('workspace_id', '=', A.id), ('ticket_ref', '=', 'TCK-HTTP-7')]):
    env['ts.emergency.access'].with_user(mgr).create({'workspace_id': A.id, 'kind': 'support', 'ticket_ref': 'TCK-HTTP-7', 'reason': 'کمک به مالک برای بررسی تنظیمات پنل'})
env.cr.commit()
print('IDS', A.id, B.id, mc.id, mb.id)
""" % L
out = shell(code)
mm = re.search(r'IDS (\d+) (\d+) (\d+) (\d+)', out)
assert mm, out[-1500:]
A, B, MC, MB = mm.groups()
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


def post(c, path, data=None):
    pairs = list((data or {}).items())
    pairs.append(('csrf_token', c.csrf(c.req('/web/login')[2])))
    return c.req(path, pairs)


def q(sql):
    o = shell("cr = env.cr; cr.execute(%r); print('Q', cr.fetchall())" % sql)
    m = re.findall(r'^Q (.*)$', o, re.M)
    return m[-1] if m else o


own, c1, oth = login('owner'), login('c1'), login('other')

# ---- the page
st, body = get(own, WA + '/audit')
check('the owner opens the audit page, one h1', st == 200 and body.count('<h1') == 1 and 'ممیزی پنل' in body, str(st))
check('...events are plain sentences', 'عضوی را افزود' in body)
check('...the support access is listed with its ticket', 'TCK-HTTP-7' in body and 'پشتیبانی' in body)
check('...nothing of another panel appears', 'TCK-HTTP-OTHER' not in body and 'خروجی گرفت' not in body.replace('از ممیزی پنل خروجی گرفت', ''))
check('a counselor gets the 403 page', get(c1, WA + '/audit')[0] == 403)
check('a member of another panel gets a 404', get(oth, WA + '/audit')[0] == 404)
check('an anonymous visitor is sent to sign in', Client(TS).req(WA + '/audit')[0] in (302, 303))
e = Client('www.eot.ir'); e.login(L['owner'], pw[L['owner']])
check('eot.ir does not serve it', e.req(WA + '/audit')[0] == 404)
check('the menu shows the audit item to the owner only', WA + '/audit' in get(own, WA)[1] and WA + '/audit' not in get(c1, WA)[1])
check('a family filter narrows the list', 'عضوی را افزود' not in get(own, WA + '/audit?family=exports')[1])
check('a member filter works', 'عضوی را افزود' in get(own, WA + '/audit?member=%s' % MC)[1])
check('a member of another panel in the filter is ignored', get(own, WA + '/audit?member=%s' % MB)[0] == 200)
check('hostile filter values are ignored, not an error', get(own, WA + "/audit?from=x'&to=%00&family=<script>&page=-1")[0] == 200)
check('the other panel sees its own audit page with its own event', 'خروجی گرفت' in get(oth, WB + '/audit')[1])

# ---- export
st, loc, _ = own.req(WA + '/audit/export')
check('the export asks for a fresh re-authentication', st in (302, 303) and '/my/reauth' in (loc or ''), '%s %s' % (st, loc))
post(own, '/my/reauth/verify', {'password': pw[L['owner']], 'next': WA + '/audit/export'})
st, loc, body = own.req(WA + '/audit/export')
check('after re-authentication the CSV downloads', st == 200 and body.startswith('﻿') and 'تاریخ (شمسی)' in body, str(st))
check('...with the plain sentence and no other panel\'s rows', 'عضوی را افزود' in body and 'secretmark' not in body)
check('...and the export itself is an audit event', q("select count(*) > 0 from ts_audit_event where event_type = 'audit.export' and workspace_id = %s" % A) == '[(True,)]')
check('a counselor cannot export', get(c1, WA + '/audit/export')[0] == 403)
check('eot.ir does not serve the export', e.req(WA + '/audit/export')[0] == 404)

summary()
