#!/usr/bin/env python3
"""Panel v2 S13 (results, print, group report) over HTTP against a served CLONE:  ts_http_pv2_13.py DB PORT"""
import importlib.util, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
NAMES = ('owner', 'c1', 'c2', 'hr', 'other')
L = {n: 'ts.pv2s13.%s.http@example.invalid' % n for n in NAMES}
pw = {u: ensure_user(u) for u in L.values()}

code = r"""
L = %r
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
A = panel('پنل S13 آموزشی', 'education'); B = panel('پنل S13 کاری', 'employment'); O = panel('پنل S13 دیگر', 'employment')
member(A, 'owner', 'owner'); m1 = member(A, 'c1', 'counselor'); member(A, 'c2', 'counselor'); member(B, 'hr', 'hr_admin'); member(O, 'other', 'owner')
talent = env['ts.instrument'].search([('code', '=', 'TALENT-INV-15')], limit=1)
plain = env['ts.instrument'].search([('state', '=', 'published'), ('purpose', '=', 'employment')], limit=1)
portal = env.ref('base.group_portal')
def puser(i):
    login = 'ts.pv2s13.part%%d.http@example.invalid' %% i
    return env['res.users'].search([('login', '=', login)]) or env['res.users'].with_context(no_reset_password=True).create(
        {'name': 'p%%d' %% i, 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})
def finish(att):
    att.give_consent()
    for it in att.active_items():
        att.save_answer(it.id, 1 + it.id %% 5)
    att.action_submit()
def finish_matrix(att):
    att.give_consent()
    items = att.active_items()
    for n, label in enumerate(['ریاضی', 'هنر']):
        f = att.ts_add_field(label)
        for i, it in enumerate(items):
            att.ts_save_cell(f, it.id, (i * (n %% 3 + 1) + 2 * n + i // 5) %% 5 + 1)
        att.ts_finish_field(f)
    assert att.action_submit()
Asg = env['ts.assignment']
def one(ws, inst, nm, i, share=True, resp=None):
    a = Asg.search([('workspace_id', '=', ws.id), ('invitee_name', '=', nm)], limit=1)
    if not a:
        a = Asg.create({'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': nm, 'responsible_id': resp.id if resp else False})
        at = a.action_accept(puser(i), share=share)
        (finish_matrix if inst.code == 'TALENT-INV-15' else finish)(at)
    return a
t1 = one(A, talent, 'دانش‌آموز گزارش یک', 1, resp=m1)
p1 = one(B, plain, 'کارجوی گزارش یک', 2)
p2 = one(B, plain, 'کارجوی گزارش دو', 3, share=False)
env.cr.commit()
print('IDS', A.id, B.id, O.id, t1.client_id.id, t1.attempt_id.id, t1.id, p1.client_id.id, p1.attempt_id.id, p1.id, p2.client_id.id, p2.attempt_id.id)
""" % L
out = shell(code)
mm = re.search(r'IDS ' + ' '.join([r'(\d+)'] * 11), out)
assert mm, out[-1500:]
A, B, O, tc, tat, ta, pc, pat, pa, uc, uat = mm.groups()
WA, WB, WO = '/my/workspaces/%s' % A, '/my/workspaces/%s' % B, '/my/workspaces/%s' % O
RT = '%s/clients/%s/r/%s' % (WA, tc, tat)        # the talent profile (education level)
RP = '%s/clients/%s/r/%s' % (WB, pc, pat)        # a shared summary
RU = '%s/clients/%s/r/%s' % (WB, uc, uat)        # not shared: status only


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


own, c1, c2, hr, oth = login('owner'), login('c1'), login('c2'), login('hr'), login('other')

# ---- the profile at education level (P12)
st, body = get(own, RT)
check('the owner opens the talent profile of a shared result', st == 200 and 'tt-report' in body, str(st))
check('...with a back link to the participant and a print form', ('/clients/%s' % tc) in body and (RT + '/print') in body)
check('the responsible counselor opens it too', get(c1, RT)[0] == 200)
check('another counselor of the panel gets a 404', get(c2, RT)[0] == 404)
check('a member of another panel gets a 404', get(oth, RT)[0] == 404)
check('an anonymous visitor is sent to sign in', Client(TS).req(RT)[0] in (302, 303))
e = Client('www.eot.ir'); e.login(L['owner'], pw[L['owner']])
check('eot.ir does not serve results', e.req(RT)[0] == 404)
check('opening a result is audited', q("select count(*) > 0 from ts_audit_event where event_type = 'result.view' and res_id = %s" % tat) == '[(True,)]')
check('a refused open is audited as a deny', q("select count(*) > 0 from ts_audit_event where event_type = 'authz.deny' and detail like '%%no_result%%'") == '[(True,)]')

# ---- ordinary instruments: bands in the shell (G29, P12)
st, body = get(hr, RP)
check('hr opens a shared summary: bands, one h1, no score column', st == 200 and body.count('<h1') == 1 and 'ts-band' in body and 'نمره (۱ تا ۵)' not in body, str(st))
check('...inside the panel shell with its menu', 'tsp-nav' in body and 'گزارش‌ها' in body)
st, body = get(hr, RU)
check('an unshared result shows the status page, no band', st == 200 and 'قابل نمایش نیست' in body and 'ts-band' not in body, str(st))
check('the owner of another panel gets a 404 on it', get(oth, RP)[0] == 404)
check('a result of another panel under this panel\'s URL is a 404', get(hr, '%s/clients/%s/r/%s' % (WB, tc, tat))[0] == 404)

# ---- printing is logged
st, loc, _ = hr.req(RP + '/print')
check('print is POST only', st in (404, 405))
check('print without CSRF is rejected', hr.req(RP + '/print', [('x', '1')])[0] in (400, 403))
st, loc, _ = post(hr, RP + '/print')
check('print redirects back with ?print=1', st in (302, 303) and (loc or '').endswith('?print=1'), '%s %s' % (st, loc))
check('...and writes a print event', q("select count(*) from ts_audit_event where event_type = 'result.print' and res_id = %s" % pat) != '[(0,)]')
st, body = get(hr, RP + '?print=1')
check('the page asked to print marks itself for the print script', 'data-tsp-autoprint' in body)
check('a plain visit does not', 'data-tsp-autoprint' not in get(hr, RP)[1])

# ---- the old routes land on the new page
st, loc, _ = hr.req('%s/a/%s' % (WB, pa))
check('the old invitation result URL redirects to the new page', st in (302, 303) and (loc or '').endswith('/r/%s' % pat), '%s %s' % (st, loc))
st, loc, _ = own.req('%s/p/%s' % (WA, tat))
check('the old profile URL redirects to the new page', st in (302, 303) and (loc or '').endswith('/r/%s' % tat), '%s %s' % (st, loc))

# ---- entry page and menu
st, body = get(own, WA + '/reports')
check('the entry page lists openable results, one h1', st == 200 and body.count('<h1') == 1 and RT in body, str(st))
check('the menu has the reports item', WA + '/reports' in get(own, WA)[1])
check('a member of another panel gets 404', get(oth, WA + '/reports')[0] == 404)

# ---- group report
st, body = get(hr, WB + '/reports/group')
check('hr opens the group report', st == 200 and body.count('<h1') == 1, str(st))
check('...with one shared result it shows the threshold sentence, no table', 'برای گزارش گروهی دست‌کم ۵ نتیجه' in body and 'کم</th>' not in body)
check('...and the n of m line', '۱ از ۲ نفر' in body)
st, body = get(c1, WA + '/reports/group')
check('a counselor opens it but sees only their own clients: below the threshold', st == 200 and 'برای گزارش گروهی دست‌کم ۵ نتیجه' in body)
check('the owner of the education panel opens it', get(own, WA + '/reports/group')[0] == 200)
check('eot.ir does not serve it', e.req(WB + '/reports/group')[0] == 404)
check('a hostile filter value is ignored, not an error', get(hr, WB + '/reports/group?group_id=x%27&period=abc')[0] == 200)
check('no person name appears in the group report', 'کارجوی گزارش' not in get(hr, WB + '/reports/group')[1])

summary()
