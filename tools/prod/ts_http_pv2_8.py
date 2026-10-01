#!/usr/bin/env python3
"""Panel v2 S8 (import) over HTTP against a served CLONE:  ts_http_pv2_8.py DB PORT"""
import http.server, importlib.util, json, os, re, sys, threading, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
NAMES = ('owner', 'c1', 'c2', 'hm', 'gowner')
L = {n: 'ts.pv2s8.%s.http@example.invalid' % n for n in NAMES}
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

code = r"""
L = %r
def user(n): return env['res.users'].search([('login', '=', L[n])])
def panel(name, purpose, approved=True):
    org = env['res.partner'].search([('name', '=', name)], limit=1) or env['res.partner'].create({'name': name, 'is_company': True})
    org.write({'is_company': True})
    ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create(
        {'name': name, 'purpose': purpose, 'partner_id': org.id})
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
A = panel('پنل S8 آموزشی', 'education'); B = panel('پنل S8 کاری', 'employment'); G = panel('پنل S8 در انتظار', 'employment', approved=False)
member(A, 'owner', 'owner'); member(A, 'c1', 'counselor'); member(A, 'c2', 'counselor')
member(B, 'owner', 'owner'); member(B, 'hm', 'hiring_manager'); member(G, 'gowner', 'owner')
cr = env.cr; ws3 = (A.id, B.id, G.id)
cr.execute("delete from ts_panel_client_group_rel where client_id in (select id from ts_panel_client where workspace_id = %%s)", [A.id])
cr.execute("delete from ts_panel_client where workspace_id = %%s", [A.id])
cr.execute("delete from ts_panel_group where workspace_id = %%s", [A.id])
cr.execute("delete from ir_attachment where res_model = 'ts.job' and res_id in (select id from ts_job where workspace_id in %%s)", [ws3])
cr.execute("delete from ts_job where workspace_id in %%s", [ws3])
env['ir.config_parameter'].sudo().set_str('ts_panel.job_inline_rows', '500')
env.cr.commit()
print('IDS', A.id, B.id, G.id)
""" % L
out = shell(code)
mm = re.search(r'IDS (\d+) (\d+) (\d+)', out)
assert mm, out[-1500:]
A, B, G = mm.groups()
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


def upload(c, path, filename, data):
    boundary = '----tsb8' + os.urandom(6).hex()
    tok = c.csrf(c.req('/web/login')[2])
    body = b''.join([
        ('--%s\r\nContent-Disposition: form-data; name="csrf_token"\r\n\r\n%s\r\n' % (boundary, tok)).encode(),
        ('--%s\r\nContent-Disposition: form-data; name="file"; filename="%s"\r\nContent-Type: application/octet-stream\r\n\r\n' % (boundary, filename)).encode(),
        data, ('\r\n--%s--\r\n' % boundary).encode()])
    r = urllib.request.Request(lib.BASE + path, data=body, headers={
        'Host': c.host, 'X-Forwarded-Proto': 'https', 'Content-Type': 'multipart/form-data; boundary=' + boundary})
    try:
        resp = c.op.open(r, timeout=60)
        return resp.status, resp.headers.get('Location', ''), resp.read().decode('utf-8', 'ignore')
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get('Location', ''), e.read().decode('utf-8', 'ignore')


def raw(c, path):
    r = urllib.request.Request(lib.BASE + path, headers={'Host': c.host, 'X-Forwarded-Proto': 'https'})
    try:
        resp = c.op.open(r, timeout=60)
        return resp.status, resp.headers.get('Content-Type', ''), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, '', b''


def q(sql):
    out = shell("cr = env.cr; cr.execute(%r); print('Q', cr.fetchall())" % sql)
    m = re.findall(r'^Q (.*)$', out, re.M)
    return m[-1] if m else out


own, c1, hm, gown = login('owner'), login('c1'), login('hm'), login('gowner')
HEAD = 'نام,کد,موبایل,ایمیل,گروه,گروه سنی\n'
FILE = (HEAD + 'علی رضایی,A1,۰۹۱۲۳۴۵۶۷۸۹,ali@example.com,کلاس الف,بزرگسال\n'
        'سارا محمدی,A2,09121112233,,کلاس الف,زیر 18\n'
        'نیما,A3,,nima@example.com,,\n'
        'خراب‌شده,A4,12,,,\n').encode('utf-8')

# ---- step 1
st, body = get(own, W + '/import')
check('the import page opens with the template link and the limits', st == 200 and 'import/template.csv' in body and body.count('<h1') == 1 and '۲۰۰۰' in body, str(st))
st, ct, data = raw(own, W + '/import/template.csv')
check('the template is a UTF-8 CSV with a BOM and the six headers', st == 200 and 'text/csv' in ct and data.startswith(b'\xef\xbb\xbf') and 'گروه سنی'.encode() in data)
check('the menu has the import item', W + '/import' in get(own, W)[1])
st, body = get(hm, '/my/workspaces/%s/import' % B)
check('a hiring manager gets the 403 page', st == 403, str(st))
st, body = get(gown, '/my/workspaces/%s/import' % G)
check('a panel waiting for approval shows the pending text', st == 200 and 'پس از تأیید' in body and 'type="file"' not in body, str(st))
check('an anonymous visitor is sent to sign in', Client(TS).req(W + '/import')[0] in (302, 303))
e = Client('www.eot.ir')
e.login(L['owner'], pw[L['owner']])
check('eot.ir does not serve the import', e.req(W + '/import')[0] == 404)

# ---- upload checks
st, loc, _ = upload(own, W + '/import/upload', 'x.txt', FILE)
st, body = get(own, path_of(loc))
check('a .txt file is refused with a message', 'فقط فایل csv یا xlsx' in body, loc)
st, loc, _ = upload(own, W + '/import/upload', 'big.csv', b'a,b\n' + b'x' * (2 * 1024 * 1024 + 10))
st, body = get(own, path_of(loc))
check('a file over 2 MB is refused', 'حجم فایل بیش از ۲ مگابایت' in body)
st, loc, _ = upload(own, W + '/import/upload', 'bin.csv', b'\x00\x01\x02\x03abc')
st, body = get(own, path_of(loc))
check('a binary file named .csv is refused', 'محتوای فایل' in body)
check('nothing was stored by the refused uploads', q("select count(*) from ts_job where workspace_id = %s" % A) == '[(0,)]')

# ---- the wizard
st, loc, _ = upload(own, W + '/import/upload', 'list.csv', FILE)
m = re.search(r'/import/(\d+)/map', loc or '')
check('a good file leads to the mapping step', st in (302, 303) and m, loc)
jid = m.group(1)
st, body = get(own, W + '/import/%s/map' % jid)
check('the mapping step preselects the columns by header', st == 200 and re.search(r'name="col_0".*?value="name" selected', body, re.S) and re.search(r'name="col_2".*?value="phone" selected', body, re.S), str(st))
st, loc, _ = post(own, W + '/import/%s/map' % jid, {'col_0': 'code', 'col_1': ''})
st, body = get(own, path_of(loc))
check('a mapping without a name column is refused with a message', 'ستونی برای «نام»' in body)
pairs = {'col_0': 'name', 'col_1': 'code', 'col_2': 'phone', 'col_3': 'email', 'col_4': 'group', 'col_5': 'age_group'}
st, loc, _ = post(own, W + '/import/%s/map' % jid, pairs)
check('a good mapping leads to the review', st in (302, 303) and loc.endswith('/import/%s/review' % jid), loc)
st, body = get(own, W + '/import/%s/review' % jid)
check('the review shows three new people and one error with its reason', st == 200 and re.search(r'شرکت‌کنندهٔ تازه</dt><dd>۳<', body) and 'ردیف ۵' in body and 'شمارهٔ موبایل معتبر نیست' in body, str(st))
check('the review wrote nothing', q("select count(*) from ts_panel_client where workspace_id = %s" % A) == '[(0,)]')
st, loc, _ = post(own, W + '/import/%s/start' % jid, {})
check('starting leads to the job page', st in (302, 303) and loc.endswith('/jobs/%s' % jid), loc)
st, body = get(own, W + '/jobs/%s' % jid)
check('the job page says it is done with the counts and offers the error report', st == 200 and 'انجام شد' in body and 'دریافت گزارش' in body and 'campaigns/new' in body, str(st))
check('three clients were created from the file, with the groups', q("select count(*) from ts_panel_client where workspace_id = %s and source = 'csv'" % A) == '[(3,)]'
      and q("select count(*) from ts_panel_group where workspace_id = %s" % A) == '[(1,)]')
check('the uploaded file was deleted', q("select count(*) from ir_attachment where res_model = 'ts.job' and res_id = %s and name = 'import-source'" % jid) == '[(0,)]')
st, ct, data = raw(own, W + '/jobs/%s/download' % jid)
txt = data.decode('utf-8', 'ignore')
check('P21: the requester downloads the error report: row numbers and reasons only', st == 200 and 'ردیف' in txt and 'خراب‌شده' not in txt and '12' not in txt.replace('۱۲', ''), str(st))
check('the download is audited', q("select count(*) from ts_audit_event where event_type = 'job.download' and workspace_id = %s" % A) != '[(0,)]')
check('P21: another member cannot open the job page', get(c1, W + '/jobs/%s' % jid)[0] == 404)
check('P21: another member cannot download', raw(c1, W + '/jobs/%s/download' % jid)[0] == 404)
check('another member cannot open its mapping or review either', get(c1, W + '/import/%s/review' % jid)[0] == 404)
check('a job id that does not exist is 404', get(own, W + '/jobs/999999')[0] == 404)

# ---- again: idempotent
st, loc, _ = upload(own, W + '/import/upload', 'list.csv', FILE)
j2 = re.search(r'/import/(\d+)/map', loc).group(1)
post(own, W + '/import/%s/map' % j2, pairs)
st, body = get(own, W + '/import/%s/review' % j2)
check('the same file again: nobody is new, three are unchanged', re.search(r'بدون تغییر</dt><dd>۳<', body) and re.search(r'شرکت‌کنندهٔ تازه</dt><dd>۰<', body))
post(own, W + '/import/%s/start' % j2, {})
check('and no duplicate was created', q("select count(*) from ts_panel_client where workspace_id = %s" % A) == '[(3,)]')

# ---- a long file waits for the runner
shell("env['ir.config_parameter'].sudo().set_str('ts_panel.job_inline_rows', '2'); env.cr.commit()")
big = (HEAD + ''.join('نفر %d,Q%d,,,,\n' % (i, i) for i in range(5))).encode('utf-8')
st, loc, _ = upload(own, W + '/import/upload', 'big.csv', big)
j3 = re.search(r'/import/(\d+)/map', loc).group(1)
post(own, W + '/import/%s/map' % j3, pairs)
post(own, W + '/import/%s/start' % j3, {})
st, body = get(own, W + '/jobs/%s' % j3)
check('a long file is queued and the page refreshes itself', 'در صف' in body and 'http-equiv="refresh"' in body, str(st))
shell("print('RAN', env['ts.job']._cron_run_jobs()); env.cr.commit()")
st, body = get(own, W + '/jobs/%s' % j3)
check('after the runner the job is done and the refresh is off', 'انجام شد' in body and 'http-equiv="refresh"' not in body)
check('the five people were created', q("select count(*) from ts_panel_client where workspace_id = %s and code like 'Q%%'" % A) == '[(5,)]')
shell("env['ir.config_parameter'].sudo().set_str('ts_panel.job_inline_rows', '500'); env.cr.commit()")

# ---- expiry
shell("env.cr.execute(\"update ts_job set expires_at = now() - interval '1 hour' where id = %s\"); env.cr.commit()" % jid)
check('an expired job is not downloadable', raw(own, W + '/jobs/%s/download' % jid)[0] == 404)

srv.shutdown()
shell("""
c = env.company.sudo(); icp = env['ir.config_parameter'].sudo()
icp.set_str('ts_kavenegar.api_base', '%s' if '%s' != '-' else '')
c.write({'kv_enabled': bool(%s), 'ts_sms_invite': bool(%s)})
env.commit() if False else env.cr.commit()
""" % (prev[0], prev[0], prev[1], prev[2]))
summary()
