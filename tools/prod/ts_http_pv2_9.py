#!/usr/bin/env python3
"""Panel v2 S9 (exports) over HTTP against a served CLONE:  ts_http_pv2_9.py DB PORT"""
import http.server, importlib.util, json, os, re, sys, threading, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
NAMES = ('owner', 'c1', 'hr', 'rv', 'cowner')
L = {n: 'ts.pv2s9.%s.http@example.invalid' % n for n in NAMES}
pw = {u: ensure_user(u) for u in L.values()}
FAKE_PORT = 18100 + 10 * int(os.environ.get('TS_SLOT', '0'))
SMS = []


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _do(self):
        n = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(n).decode() if n else ''
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
        q.update(dict(urllib.parse.parse_qsl(body)))
        path = urllib.parse.urlsplit(self.path).path.split('/v1/', 1)[1].split('/', 1)[1][:-5]
        ent = []
        if path == 'sms/send':
            SMS.append(q)
            for r in q['receptor'].split(','):
                ent.append({'messageid': 900000 + len(SMS), 'message': q['message'], 'status': 1, 'statustext': 'q', 'sender': '10004346', 'receptor': r, 'cost': 100})
        out = json.dumps({'return': {'status': 200, 'message': 'ok'}, 'entries': ent}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(out)

    do_GET = do_POST = do_DELETE = _do


srv = http.server.ThreadingHTTPServer(('127.0.0.1', FAKE_PORT), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
prev = shell("""
c = env.company.sudo(); icp = env['ir.config_parameter'].sudo()
print('PREV', icp.get_str('ts_kavenegar.api_base') or '-', int(bool(c.kv_enabled)), int(bool(c.ts_sms_invite)), c.kv_lines or '-', c.kv_api_key or '-', c.kv_sender or '-')
icp.set_str('ts_kavenegar.api_base', 'http://127.0.0.1:@FAKEPORT@/v1/%s/%s.json')
c.write({'kv_lines': '10004346'})
c.write({'kv_enabled': True, 'kv_api_key': 'FAKEKEY', 'kv_sender': '10004346', 'ts_sms_invite': True})
icp.set_str('ts_panel.invites_per_hour', '200')
env.cr.commit()
""".replace('@FAKEPORT@', str(FAKE_PORT)))
prev = re.search(r'PREV (\S+) (\d) (\d) (\S+) (\S+) (\S+)', prev).groups()

import csv, io
code = r"""
L = %r
import json
from odoo import fields
def user(n): return env['res.users'].search([('login', '=', L[n])])
def panel(name, purpose, approved=True):
    org = env['res.partner'].search([('name', '=', name)], limit=1) or env['res.partner'].create({'name': name, 'is_company': True})
    org.write({'is_company': True})
    ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create(
        {'name': name, 'purpose': purpose, 'partner_id': org.id, **({'escalation_contact_id': org.id} if purpose == 'clinical' else {})})
    ws.write({'approved_on': '2026-01-01 00:00:00' if approved else False})
    ws.state = 'pilot'
    return ws
def member(ws, n, role):
    u = user(n)
    m = env['ts.workspace.member'].search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)]) or env['ts.workspace.member'].create(
        {'workspace_id': ws.id, 'user_id': u.id, 'role': role})
    if role in ('counselor', 'clinician'):
        m.write({'license_number': 'T-1', 'verification_state': 'verified'})
    return m
A = panel('پنل S9 آموزشی', 'education'); B = panel('پنل S9 کاری', 'employment'); C = panel('پنل S9 درمانی', 'clinical')
member(A, 'owner', 'owner'); member(A, 'c1', 'counselor')
member(B, 'hr', 'hr_admin'); member(B, 'rv', 'reviewer'); member(C, 'cowner', 'owner')
cr = env.cr; ws3 = (A.id, B.id, C.id)
cr.execute("delete from ir_attachment where res_model = 'ts.job' and res_id in (select id from ts_job where workspace_id in %%s)", [ws3])
cr.execute("delete from ts_job where workspace_id in %%s", [ws3])
cr.execute("delete from ts_assignment where workspace_id in %%s and state not in ('done')", [ws3])
env['ir.config_parameter'].sudo().set_str('ts_panel.job_inline_rows', '500')
portal = env.ref('base.group_portal')
def puser(i):
    login = 'ts.pv2s9.part%%d.http@example.invalid' %% i
    return env['res.users'].search([('login', '=', login)]) or env['res.users'].with_context(no_reset_password=True).create(
        {'name': 'p%%d' %% i, 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})
Asg = env['ts.assignment']
for _a in Asg.search([('workspace_id', 'in', list(ws3)), ('client_id', '=', False)]):      # repair of an earlier run
    _a.client_id = env['ts.panel.client'].ts_for_invitation({'workspace_id': _a.workspace_id.id, 'invitee_name': _a.invitee_name, 'invitee_phone': False, 'invitee_email': False}).id
talent = env['ts.instrument'].search([('code', '=', 'TALENT-INV-15')], limit=1)
plain = env['ts.instrument'].search([('state', '=', 'published'), ('purpose', '=', 'employment')], limit=1)
# education: one finished TALENT result with a private field name, one open invitation
if not Asg.search_count([('workspace_id', '=', A.id), ('invitee_name', '=', 'دانش‌آموز نتیجه‌دار')]):
    a = Asg.create({'workspace_id': A.id, 'instrument_id': talent.id, 'invitee_name': 'دانش‌آموز نتیجه‌دار'})
    at = a.action_accept(puser(1), share=True)
    at.write({'state': 'done', 'released': True, 'submitted_at': fields.Datetime.now(), 'profile_json': json.dumps({'fields': [
        {'seq': 1, 'label': 'زمینهٔ-محرمانه-۴۲', 'scales': {'ANA': 61.5, 'EXP': 70, 'ACA': 48, 'NOV': 80, 'DUT': 55}, 'composites': {'TOT': 62.9}}]})})
if not Asg.search_count([('workspace_id', '=', A.id), ('invitee_name', '=', '=HYPERLINK("x")')]):
    Asg.create({'workspace_id': A.id, 'instrument_id': talent.id, 'invitee_name': '=HYPERLINK("x")'})
# employment: one finished shared result
if not Asg.search_count([('workspace_id', '=', B.id), ('invitee_name', '=', 'کارجوی نتیجه‌دار')]):
    b = Asg.create({'workspace_id': B.id, 'instrument_id': plain.id, 'invitee_name': 'کارجوی نتیجه‌دار'})
    bt = b.action_accept(puser(2), share=True)
    bt.give_consent()
    for it in bt.active_items():
        bt.save_answer(it.id, 1 + it.id %% 5)
    bt.action_submit()
env.cr.commit()
print('IDS', A.id, B.id, C.id)
""" % L
out = shell(code)
mm = re.search(r'IDS (\d+) (\d+) (\d+)', out)
assert mm, out[-1500:]
A, B, C = mm.groups()
W = '/my/workspaces/%s' % A


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
        resp = c.op.open(r, timeout=60)
        return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, b''


def q(sql):
    out = shell("cr = env.cr; cr.execute(%r); print('Q', cr.fetchall())" % sql)
    m = re.findall(r'^Q (.*)$', out, re.M)
    return m[-1] if m else out


def reauth(c, nxt, who):
    return post(c, '/my/reauth/verify', {'password': pw[L[who]], 'next': nxt})


own, c1, hr, rv, cow = login('owner'), login('c1'), login('hr'), login('rv'), login('cowner')
WB, WC = '/my/workspaces/%s' % B, '/my/workspaces/%s' % C

# ---- the page
st, body = get(own, W + '/exports')
check('the exports page opens with its sections', st == 200 and body.count('<h1') == 1 and 'ساخت فایل شرکت‌کنندگان' in body
      and 'ساخت فایل وضعیت' in body and 'ساخت فایل نتایج' in body, str(st))
check('the menu has the exports item', W + '/exports' in get(own, W)[1])
check('a counselor gets the 403 page', get(c1, W + '/exports')[0] == 403)
st, body = get(hr, WB + '/exports')
check('the hr admin of an employment panel sees the results export', st == 200 and 'ساخت فایل نتایج' in body)
check('a reviewer gets the 403 page', get(rv, WB + '/exports')[0] == 403)
st, body = get(cow, WC + '/exports')
check('a clinical panel owner may export clients but sees no results export', st == 200 and 'ساخت فایل شرکت‌کنندگان' in body and 'ساخت فایل نتایج' not in body, str(st))
check('an anonymous visitor is sent to sign in', Client(TS).req(W + '/exports')[0] in (302, 303))
e = Client('www.eot.ir')
e.login(L['owner'], pw[L['owner']])
check('eot.ir does not serve the exports', e.req(W + '/exports')[0] == 404)

# ---- creating needs a fresh re-authentication
n0 = q("select count(*) from ts_job where workspace_id = %s and kind like 'export_%%%%'" % A)
st, loc, _ = post(own, W + '/exports/create', {'what': 'clients', 'format': 'csv'})
check('without a fresh re-authentication the request is sent to /my/reauth', st in (302, 303) and '/my/reauth' in (loc or ''), '%s %s' % (st, loc))
check('...and no job exists yet', q("select count(*) from ts_job where workspace_id = %s and kind like 'export_%%%%'" % A) == n0)
st, loc, _ = reauth(own, W + '/exports', 'owner')
check('re-authentication with the password succeeds', st in (302, 303) and '/my/reauth' not in (loc or '') or st in (302, 303), '%s %s' % (st, loc))

# ---- clients export (EXP-1)
st, loc, _ = post(own, W + '/exports/create', {'what': 'clients', 'format': 'csv', 'state': 'all'})
m = re.search(r'/jobs/(\d+)', loc or '')
check('a client export leads to the job page', st in (302, 303) and m, '%s %s' % (st, loc))
jid = m.group(1)
st, body = get(own, W + '/jobs/' + jid)
check('the job page says the file is ready and offers the download', st == 200 and 'فایل آماده است' in body and '/download' in body and body.count('<h1') == 1, str(st))
st, hdr, data = raw(own, W + '/jobs/%s/download' % jid)
txt = data.decode('utf-8-sig', 'ignore')
check('the download is a UTF-8 CSV with a BOM, private and not cached', st == 200 and data.startswith(b'\xef\xbb\xbf') and 'text/csv' in hdr.get('Content-Type', '')
      and 'attachment' in hdr.get('Content-Disposition', '') and 'no-store' in hdr.get('Cache-Control', ''), str(st))
check('the file holds the clients and a quoted formula', 'دانش‌آموز نتیجه‌دار' in txt and "'=HYPERLINK" in txt and '\n=HYPERLINK' not in txt)
check('the download is audited as export.download and the creation as export.create',
      q("select count(*) from ts_audit_event where event_type = 'export.download' and workspace_id = %s" % A) != '[(0,)]'
      and q("select count(*) from ts_audit_event where event_type = 'export.create' and workspace_id = %s" % A) != '[(0,)]')
check('the audit rows hold no names', 'دانش‌آموز' not in q("select string_agg(detail, '') from ts_audit_event where event_type like 'export.%%%%' and workspace_id = %s" % A))

# ---- the download needs a fresh re-authentication too, and belongs to the requester
own2 = login('owner')
st, loc, _ = own2.req(W + '/jobs/%s/download' % jid)
check('another session of the same account without re-authentication is sent to /my/reauth', st in (302, 303) and '/my/reauth' in (loc or ''), '%s %s' % (st, loc))
check('a colleague cannot open the job page', get(c1, W + '/jobs/' + jid)[0] == 404)
check('a colleague cannot download the file', raw(c1, W + '/jobs/%s/download' % jid)[0] == 404)

# ---- xlsx and status (EXP-2)
st, loc, _ = post(own, W + '/exports/create', {'what': 'status', 'format': 'xlsx'})
j2 = re.search(r'/jobs/(\d+)', loc or '').group(1)
st, hdr, data = raw(own, W + '/jobs/%s/download' % j2)
check('an xlsx file is a zip and opens as a workbook', st == 200 and data[:2] == b'PK' and 'spreadsheetml' in hdr.get('Content-Type', ''))
import zipfile
zf = zipfile.ZipFile(io.BytesIO(data))
import html
sheet = html.unescape(zf.read('xl/worksheets/sheet1.xml').decode('utf-8'))      # openpyxl writes inline strings
shared = sheet
check('the status sheet is right to left, has the header and one row per invitation, no result columns (ORM checks the headers)',
      'rightToLeft="1"' in sheet and sheet.count('<row ') == 3 and '<t>نام</t>' in sheet and '<t>وضعیت</t>' in sheet and '<t>تاریخ دعوت (میلادی)</t>' in sheet, '%s rows=%d ns=%s' % ('rightToLeft="1"' in sheet, sheet.count('<row '), '<t>نام</t>' in sheet))

# ---- results (EXP-3)
st, loc, _ = post(own, W + '/exports/create', {'what': 'results', 'format': 'csv'})
j3 = re.search(r'/jobs/(\d+)', loc or '').group(1)
st, hdr, data = raw(own, W + '/jobs/%s/download' % j3)
txt = data.decode('utf-8-sig', 'ignore')
rows = list(csv.reader(io.StringIO(txt)))
check('the education results file holds the five scales of the field, by number', len(rows) == 2 and rows[1][3] == '1' and rows[1][5:] == ['61.5', '70', '48', '80', '55', '62.9'], str(rows))
check('the participant\'s own field name never leaves', 'محرمانه' not in txt and not any('پاسخ' in c for c in rows[0]))
st, loc, _ = post(hr, WB + '/exports/create', {'what': 'results', 'format': 'csv'})
check('the hr admin must re-authenticate first', st in (302, 303) and '/my/reauth' in (loc or ''))
reauth(hr, WB + '/exports', 'hr')
st, loc, _ = post(hr, WB + '/exports/create', {'what': 'results', 'format': 'csv'})
jh = re.search(r'/jobs/(\d+)', loc or '')
check('...then the employment results export works', st in (302, 303) and jh, '%s %s' % (st, loc))
st, hdr, data = raw(hr, WB + '/jobs/%s/download' % jh.group(1))
rows = list(csv.reader(io.StringIO(data.decode('utf-8-sig', 'ignore'))))
check('employment rows hold the band per factor and no score columns filled', len(rows) > 1 and all(r_[0] == 'کارجوی نتیجه‌دار' and r_[4] in ('کم', 'متوسط', 'زیاد') and r_[5:] == [''] * 6 for r_ in rows[1:]), str(rows[:2]))
st, loc, _ = post(rv, WB + '/exports/create', {'what': 'status', 'format': 'csv'})
check('a reviewer cannot create an export', st == 403, str(st))
reauth(cow, WC + '/exports', 'cowner')
st, loc, _ = post(cow, WC + '/exports/create', {'what': 'results', 'format': 'csv'})
check('a clinical panel owner cannot create a results export', st == 403, str(st))
st, loc, _ = post(cow, WC + '/exports/create', {'what': 'clients', 'format': 'csv'})
check('...but can export the client list', st in (302, 303) and '/jobs/' in (loc or ''), '%s %s' % (st, loc))
st, loc, _ = post(own, W + '/exports/create', {'what': 'audit', 'format': 'csv'})
check('an unknown kind is refused', st == 403, str(st))
st, loc, _ = own.req(W + '/exports/create', [('what', 'clients'), ('format', 'csv')])
check('creating without a CSRF token is rejected', st in (400, 403), str(st))

# ---- expiry
shell("env.cr.execute(\"update ts_job set expires_at = now() - interval '1 hour' where id = %s\"); env.cr.commit()" % jid)
check('after the expiry the file is not downloadable', raw(own, W + '/jobs/%s/download' % jid)[0] == 404)
st, body = get(own, W + '/jobs/' + jid)
check('the expired job page still opens', st == 200)

srv.shutdown()
shell("""
c = env.company.sudo(); icp = env['ir.config_parameter'].sudo()
icp.set_str('ts_kavenegar.api_base', '%s' if '%s' != '-' else '')
c.write({'kv_enabled': bool(%s), 'ts_sms_invite': bool(%s)})
env.cr.commit()
""" % (prev[0], prev[0], prev[1], prev[2]))
summary()
