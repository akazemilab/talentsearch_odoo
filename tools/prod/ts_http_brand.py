#!/usr/bin/env python3
"""Clinic phase 5 (ts_brand) over HTTP against a served CLONE:  ts_http_brand.py DB PORT

A counseling-center test panel: the owner saves «هویت مرکز در گزارش‌ها» on the settings page and a counselor's title on the
member page (both audited brand.change); the counselor opens their own member page (no members list) and saves their
title and bio; the participant's report and the counselor's panel result page show the institution and the counselor with
the verified licence (hidden while unverified) and the footer line; the PDF routes answer application/pdf starting with
%PDF for the participant, the responsible counselor and the (practising) owner, and 404 for a counselor of the same panel
who is not responsible; /i/<code> and /j/<code> redirect to the invitation pages (404 on eot.ir and for an unknown code);
no page title repeats the site name. Fixtures are committed on the clone (like the other HTTP suites); nothing is sent."""
import os, re, sys, importlib.util, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
NAMES = ('owner', 'c1', 'c3', 'p1')
L = {n: 'ts.brand.%s.http@example.invalid' % n for n in NAMES}
pw = {u: ensure_user(u) for u in L.values()}
PUBLIC = 'مرکز مشاوره آرامش وب'
LIC = 'LIC-HTTP-77'
FOOT = 'تهیه‌شده با استعدادیاب (از خانوادهٔ هیجان اندیشه)'

code = r"""
from odoo import fields
Command = fields.Command
L = %r
LIC = %r
def user(n): return env['res.users'].search([('login', '=', L[n])])
for n in L:
    user(n).name = {'owner': 'مالک آزمون هویت', 'c1': 'سارا مشاور آزمون', 'c3': 'مشاور دیگر آزمون', 'p1': 'شرکت‌کنندهٔ آزمون هویت'}[n]
name = 'پنل آزمون هویت وب'
org = env['res.partner'].search([('name', '=', name)], limit=1) or env['res.partner'].create({'name': name, 'is_company': True})
ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create(
    {'name': name, 'purpose': 'clinical', 'partner_id': org.id, 'escalation_contact_id': org.id})
ws.write({'approved_on': '2026-01-01 00:00:00', 'public_name': False, 'sms_name': False, 'brand_color': False, 'contact_line': False})
ws.state = 'pilot'
env.company.sudo().write({'kv_enabled': False})      # nothing is sent by this suite (the SMS suites enable their fake gateway)
def member(n, role, lic=None):
    u = user(n)
    m = env['ts.workspace.member'].with_context(active_test=False).search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)]) \
        or env['ts.workspace.member'].create({'workspace_id': ws.id, 'user_id': u.id, 'role': role})
    m.write({'active': True, 'role': role, 'title': False, 'report_bio': False, 'show_on_report': True})
    if lic:
        m.write({'license_number': lic, 'verification_state': 'verified'})
    return m
mo = member('owner', 'owner', 'OWN-HTTP-1'); mo.owner_practices = True
m1 = member('c1', 'clinician', LIC); m3 = member('c3', 'clinician', 'LIC-HTTP-3')
inst = m1.allowed_instruments().filtered(lambda i: i.audience == 'adult' and i.code != 'TALENT-INV-15') \
    .sorted(lambda i: (i.active_item_count, i.id))[:1]
p1 = user('p1')
a = env['ts.assignment'].search([('workspace_id', '=', ws.id), ('user_id', '=', p1.id), ('battery_id', '=', False),
                                 ('state', '=', 'done')], limit=1)
if not a:
    a = env['ts.assignment'].create({'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': p1.name,
                                     'invited_by_id': m1.user_id.id, 'responsible_id': m1.id})
    at = a.action_accept(p1, True)
    at.give_consent(research=False, role='self')
    for it in at.active_items():
        at.save_answer(it.id, 1 + it.id %% 5)
    at.action_submit()
a.responsible_id = m1
at = a.attempt_id
fresh = env['ts.assignment'].create({'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': 'دعوت تازهٔ آزمون',
                                     'invited_by_id': m1.user_id.id})
inv = env['ts.member.invite'].search([('workspace_id', '=', ws.id), ('state', '=', 'pending'), ('phone', '=', '09127770961')], limit=1) \
    or env['ts.member.invite'].ts_create(mo, 'clinician', phone_raw='09127770961')
bat = m1.allowed_batteries().filtered(lambda b: b.audience == 'adult')[:1]
ab = env['ts.assignment'].search([('workspace_id', '=', ws.id), ('user_id', '=', p1.id), ('battery_id', '!=', False),
                                  ('state', '=', 'done')], limit=1)
if bat and not ab:
    ab = env['ts.assignment'].create({'workspace_id': ws.id, 'battery_id': bat.id, 'invitee_name': p1.name,
                                      'invited_by_id': m1.user_id.id, 'responsible_id': m1.id})
    first = ab.action_accept(p1, True)
    first.give_consent(research=False, role='self')
    for t in ab.ts_battery_attempts():
        if t.state == 'consent':
            t.give_consent(research=False, role='self')
        for it in t.active_items():
            t.save_answer(it.id, 1 + it.id %% 5)
        t.action_submit()
env.cr.commit()
print('IDS', ws.id, mo.id, m1.id, m3.id, at.id, a.client_id.id, ab.id or 0, ab.client_id.id or 0)
print('LINKS', fresh.short_code, fresh.token, inv.short_code, inv.token)
""" % (L, LIC)
out = shell(code)
mm = re.search(r'IDS (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)', out)
assert mm, out[-2000:]
WS, MO, M1, M3, AT, CL, AB, CLB = mm.groups()
ICODE, ITOK, JCODE, JTOK = re.search(r'LINKS (\S+) (\S+) (\S+) (\S+)', out).groups()
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


def post(c, path, data):
    pairs = list(data.items()) if isinstance(data, dict) else list(data)
    pairs.append(('csrf_token', c.csrf(c.req('/web/login')[2])))
    return c.req(path, pairs)


def raw(c, path):
    r = urllib.request.Request(lib.BASE + path, headers={'Host': c.host, 'X-Forwarded-Proto': 'https'})
    try:
        resp = c.op.open(r, timeout=180)
        return resp.status, resp.headers.get('Content-Type', ''), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, '', b''


def audit_count(event, extra=''):
    o = shell("print('N', env['ts.audit.event'].search_count([('event_type', '=', %r), ('workspace_id', '=', %s)%s]))" % (event, WS, extra))
    m = re.search(r'^N (\d+)', o, re.M)
    return int(m.group(1)) if m else -1


def title_of(body):
    m = re.search(r'<title>(.*?)</title>', body, re.S)
    return (m.group(1) if m else '').strip()


own, c1, c3, p1 = login('owner'), login('c1'), login('c3'), login('p1')

# ---------------------------------------------------------------- 1. settings: the panel's identity on reports
st, body = get(own, W + '/settings')
check('owner: settings page has «هویت مرکز در گزارش‌ها» with the header preview', st == 200 and 'هویت مرکز در گزارش‌ها' in body
      and 'data-tsbr-preview' in body and 'name="sms_name"' in body, str(st))
n0 = audit_count('brand.change')
st, loc, _ = post(own, W + '/settings/brand', {'public_name': PUBLIC, 'sms_name': 'مرکز آرامش', 'brand_color': '#2A6F97',
                                               'contact_line': '۰۲۱-۸۸۸۸۸۸۸۸ · aramesh.example'})
o = shell("ws = env['ts.workspace'].browse(%s); print('WS', ws.public_name, '|', ws.sms_name, '|', ws.brand_color)" % WS)
check('owner saves the identity (server-validated, colour lower-cased)', st in (302, 303) and ('WS %s | مرکز آرامش | #2a6f97' % PUBLIC) in o, o[-200:])
check('the change is audited as brand.change', audit_count('brand.change') == n0 + 1)
st, loc, _ = post(own, W + '/settings/brand', {'public_name': PUBLIC, 'sms_name': 'ا' * 19, 'brand_color': 'red'})
st, body = get(own, W + '/settings')
check('an invalid SMS name / colour is refused with a message', 'حداکثر ۱۸ نویسه' in body or '#rrggbb' in body)
st, body = get(c1, W + '/settings')
check('a counselor has no settings page', st == 403, str(st))
st, loc, _ = post(c1, W + '/settings/brand', {'public_name': 'تغییر غیرمجاز'})
o = shell("print('PN', env['ts.workspace'].browse(%s).public_name)" % WS)
check('a counselor cannot post the identity', st == 403 and ('PN %s' % PUBLIC) in o, '%s %s' % (st, o[-80:]))

# ---------------------------------------------------------------- 2. member page: «هویت شما در گزارش‌ها»
st, body = get(own, W + '/members/' + M1)
check('owner: member page has the counselor\'s report identity (title and show on report only)', st == 200
      and 'هویت این عضو در گزارش‌ها' in body and 'name="title"' in body and 'name="signature"' not in body, str(st))
n0 = audit_count('brand.change')
st, loc, _ = post(own, W + '/members/%s/brand' % M1, {'title': 'روان‌شناس و مشاور', 'show_on_report': '1'})
check('owner sets the counselor\'s title (audited)', st in (302, 303) and audit_count('brand.change') == n0 + 1)
st, body = get(c1, W + '/members/' + M1)
check('the counselor opens their own member page without the members list', st == 200 and 'هویت شما در گزارش‌ها' in body
      and 'name="signature"' in body and 'name="photo"' in body and LIC in body, str(st))
st, loc, _ = post(c1, W + '/members/%s/brand' % M1, {'title': 'روان‌شناس و مشاور', 'report_bio': 'مشاور نوجوان و خانواده',
                                                      'show_on_report': '1'})
o = shell("m = env['ts.workspace.member'].browse(%s); print('MB', m.title, '|', m.report_bio)" % M1)
check('the counselor saves their own bio', 'MB روان‌شناس و مشاور | مشاور نوجوان و خانواده' in o, o[-160:])
st, body = get(c1, W + '/members/' + MO)
check('a counselor cannot open a colleague\'s member page', st == 403, str(st))
st, _ = get(c3, W + '/members/' + M1)
st2, loc, _ = post(c3, W + '/members/%s/brand' % M1, {'title': 'دست‌کاری'})
o = shell("print('T', env['ts.workspace.member'].browse(%s).title)" % M1)
check('another counselor cannot edit it', st == 403 and st2 == 403 and 'T روان‌شناس و مشاور' in o, '%s %s' % (st, st2))
st, body = get(c1, W)
check('the shell links every member to their own identity section', ('/members/%s#tsbr-member' % M1) in body)

# ---------------------------------------------------------------- 3. report header (participant and panel)
st, body = get(p1, '/my/assessments/' + AT)
check('participant report: institution, counselor with verified licence, footer line', st == 200 and PUBLIC in body
      and 'سارا مشاور آزمون' in body and 'روان‌شناس و مشاور' in body and LIC in body and FOOT in body and 'tsbr-head' in body, str(st))
check('participant report: brand colour as the header rule, PDF button', '--tsbr-color: #2a6f97' in body
      and '/my/assessments/%s/pdf' % AT in body)
check('participant report: the counselor\'s contact data never appears', 'ts.brand.c1.http@example.invalid' not in body)
st, body = get(c1, W + '/clients/%s/r/%s' % (CL, AT))
check('panel result page: the same header for the responsible counselor', st == 200 and PUBLIC in body and LIC in body
      and (W + '/clients/%s/r/%s/pdf' % (CL, AT)) in body, str(st))
shell("m = env['ts.workspace.member'].browse(%s); m.verification_state = 'pending'; env.cr.commit()" % M1)
st, body = get(p1, '/my/assessments/' + AT)
check('an unverified licence is hidden from the report', st == 200 and PUBLIC in body and LIC not in body, str(st))
shell("m = env['ts.workspace.member'].browse(%s); m.verification_state = 'verified'; env.cr.commit()" % M1)

# ---------------------------------------------------------------- 4. PDF downloads
n0 = audit_count('result.print')
st, ctype, pdf = raw(p1, '/my/assessments/%s/pdf' % AT)
check('participant PDF: application/pdf starting with %PDF', st == 200 and ctype.startswith('application/pdf') and pdf[:4] == b'%PDF',
      '%s %s %s' % (st, ctype, pdf[:40]))
fonts = sorted(set(re.findall(rb'/FontName\s*/([A-Za-z0-9+_-]+)', pdf)))
check('participant PDF embeds a font (Persian glyphs come from it)', bool(fonts), str(fonts[:6]))
st, ctype, pdf = raw(c1, W + '/clients/%s/r/%s/pdf' % (CL, AT))
check('responsible counselor PDF', st == 200 and ctype.startswith('application/pdf') and pdf[:4] == b'%PDF', '%s %s' % (st, ctype))
st, ctype, pdf = raw(own, W + '/clients/%s/r/%s/pdf' % (CL, AT))
check('practising owner PDF', st == 200 and ctype.startswith('application/pdf') and pdf[:4] == b'%PDF', '%s %s' % (st, ctype))
st, ctype, _ = raw(c3, W + '/clients/%s/r/%s/pdf' % (CL, AT))
check('a counselor of the same panel who is not responsible gets 404', st == 404, str(st))
st, ctype, _ = raw(c3, '/my/assessments/%s/pdf' % AT)
check('another account cannot download the participant PDF', st == 404, str(st))
check('every download is audited result.print (kind pdf)', audit_count('result.print') >= n0 + 3)
o = shell("print('ATT', env['ir.attachment'].sudo().search_count([('res_model', '=', 'ts.attempt'), ('res_id', '=', %s)]))" % AT)
check('the PDF is never stored as an attachment', 'ATT 0' in o, o[-60:])
if AB != '0':
    st, ctype, pdf = raw(p1, '/my/assessments/battery/%s/pdf' % AB)
    check('participant battery PDF', st == 200 and pdf[:4] == b'%PDF', '%s %s' % (st, ctype))
    st, ctype, pdf = raw(c1, W + '/clients/%s/b/%s/pdf' % (CLB, AB))
    check('panel battery PDF', st == 200 and pdf[:4] == b'%PDF', '%s %s' % (st, ctype))
    st, ctype, _ = raw(c3, W + '/clients/%s/b/%s/pdf' % (CLB, AB))
    check('panel battery PDF: 404 without access', st == 404, str(st))
    st, body = get(p1, '/my/assessments/battery/' + AB)
    check('participant battery page: institution header', st == 200 and PUBLIC in body and FOOT in body, str(st))

# ---------------------------------------------------------------- 5. short links
anon = Client(TS)
st, loc, _ = anon.req('/i/' + ICODE)
check('/i/<code> redirects (302) to the invitation page', st == 302 and loc.endswith('/invite/' + ITOK), '%s %s' % (st, loc))
st, loc, _ = anon.req('/j/' + JCODE)
check('/j/<code> redirects (302) to the colleague invitation page', st == 302 and loc.endswith('/join/' + JTOK), '%s %s' % (st, loc))
check('an unknown or malformed code is 404', anon.req('/i/zzzzzzzz')[0] == 404 and anon.req('/i/ABC')[0] == 404)
e = Client('www.eot.ir')
check('eot.ir does not serve /i/ or /j/', e.req('/i/' + ICODE)[0] == 404 and e.req('/j/' + JCODE)[0] == 404)
st, loc, _ = anon.req('/n/1')
check('/n/<id> leads to the notice page (which checks the reader)', st == 302 and loc.endswith('/my/notifications/1'), loc)

# ---------------------------------------------------------------- 6. titles never repeat the site name
dup = []
for c, path in ((p1, '/my/notifications'), (p1, '/my/phone'), (p1, '/my/sharing'), (p1, '/my/privacy'), (anon, '/signup'),
                (anon, '/panel'), (c1, W + '/members/' + M1), (p1, '/my/assessments/' + AT)):
    st, body = get(c, path)
    t = title_of(body)
    if st == 200 and (not t or 'استعدادیاب | استعدادیاب' in t):
        dup.append('%s: %s' % (path, t))
check('no page title repeats «استعدادیاب»', not dup, str(dup))
summary()
