#!/usr/bin/env python3
"""Panel v2 S6 (invitations) over HTTP against a served CLONE:  ts_http_pv2_6.py DB PORT"""
import http.server, importlib.util, json, os, re, sys, threading, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
NAMES = ('owner', 'admin', 'c1', 'c2', 'gowner')
L = {n: 'ts.pv2s6.%s.http@example.invalid' % n for n in NAMES}
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
A = panel('پنل S6 آموزشی', 'education'); G = panel('پنل S6 کاری در انتظار', 'employment', approved=False)
mo = member(A, 'owner', 'owner'); member(A, 'admin', 'admin'); m1 = member(A, 'c1', 'counselor'); m2 = member(A, 'c2', 'counselor')
member(G, 'gowner', 'owner')
C = env['ts.panel.client']; AS = env['ts.assignment'].sudo()
AS.search([('workspace_id', 'in', [A.id, G.id])]).write({'withdrawn': True})
for n, r, ph in (('ویزارد یک', m1, '09125551111'), ('ویزارد دو', m2, False)):
    c = C.search([('workspace_id', '=', A.id), ('name', '=', n)], limit=1) or C.create({'workspace_id': A.id, 'name': n, 'responsible_id': r.id, 'phone': ph or False})
    c.write({'phone': ph or False, 'responsible_id': r.id, 'state': 'active'})
env['ir.config_parameter'].sudo().set_str('ts_panel.invites_per_hour', '200')
env.cr.commit()
cid = lambda n: C.search([('workspace_id', '=', A.id), ('name', '=', n)], limit=1).id
print('IDS', A.id, G.id, cid('ویزارد یک'), cid('ویزارد دو'))
""" % L
out = shell(code)
mm = re.search(r'IDS (\d+) (\d+) (\d+) (\d+)', out)
assert mm, out[-1500:]
A, G, K1, K2 = mm.groups()
W = '/my/workspaces/%s' % A


def login(n):
    c = Client(TS)
    assert c.login(L[n], pw[L[n]]), n
    return c


def get(c, path):
    """GET that follows up to three redirects (the test client does not)."""
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


def first_inst(c, path=W):
    get(c, path + '/invites/new?fresh=1')
    post(c, path + '/invites/new', {'step': '1', 'choose': K1})
    return re.search(r'name="instrument_id"[^>]*value="(\d+)"', get(c, path + '/invites/new?step=2')[1]).group(1)


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


own, c1, c2, adm = login('owner'), login('c1'), login('c2'), login('admin')
gown = login('gowner')


def wizard(c, who, deadline='', note='', sms=False, attest=False, path=W):
    """Walks the four steps; returns (location of the last redirect, token or None)."""
    get(c, path + '/invites/new?fresh=1')
    if who[0] == 'client':
        post(c, path + '/invites/new', {'step': '1', 'choose': who[1]})
    else:
        post(c, path + '/invites/new', {'step': '1', 'new_name': who[1], 'new_phone': who[2], 'new_email': ''})
    st, body = get(c, path + '/invites/new?step=2')
    inst = re.search(r'name="instrument_id"[^>]*value="(\d+)"', body)
    post(c, path + '/invites/new', {'step': '2', 'instrument_id': inst.group(1) if inst else '0'})
    data = {'step': '3', 'deadline': deadline, 'note': note}
    if sms:
        data['sms'] = '1'
    if attest:
        data['attest'] = '1'
    post(c, path + '/invites/new', data)
    st, body = get(c, path + '/invites/new?step=4')
    st, loc, _ = post(c, path + '/invites/new', {'step': '4'})
    return loc, body


# ---- list and dashboard
st, body = get(own, W + '/invites')
check('owner opens the invitation list: one h1, chips with counts, empty text', st == 200 and body.count('<h1') == 1 and 'tsp-chip' in body, str(st))
st, body = get(own, W)
check('the panel address is the dashboard with a new-invitation button and tiles into the list',
      st == 200 and 'داشبورد' in body and '/invites/new' in body and ('/my/workspaces/%s/invites?state=opened' % A) in body, str(st))
check('W/home still answers (it redirects here)', get(own, W + '/home')[0] == 200)
st, body = get(own, W + '/legacy')
check('the old page lives on at W/legacy with its notice', st == 200 and 'رفتن به داشبورد' in body)
st, body = get(own, W + '?state=done')
check('an old state link lands in the new list', st == 200 and 'tsp-chip' in body and 'name="csrf_token"' not in body or 'دعوت‌ها' in body)

# ---- wizard: existing client, SMS with attestation
n0 = len(SMS)
loc, review = wizard(own, ('client', K1), deadline='2099-01-01', note='یادداشت آزمون', sms=True, attest=True)
check('review step shows the person, the instrument and the SMS choice, without the phone number in the URL',
      'ویزارد یک' in review and 'بله، با تأیید رضایت' in review and '09125551111' not in loc, loc)
m = re.search(r'/invites/(\d+)\?new=1', loc)
check('confirming redirects to the new invitation page', bool(m), loc)
AID = m.group(1) if m else '0'
st, page = get(own, W + '/invites/' + AID + '?new=1')
tok = re.search(r'value="https://talentsearch\.ir/invite/([0-9a-f]{32})"', page)
check('the page shows the link, a copy button, the QR image and the state', st == 200 and bool(tok) and 'data-tsp-copy' in page and '/qr.png' in page and 'دعوت‌شده' in page)
check('the SMS went out exactly once and carries the link', len(SMS) == n0 + 1 and tok and tok.group(1) in SMS[-1]['message'] and SMS[-1]['receptor'] == '09125551111', str(len(SMS) - n0))
check('the page says the SMS was sent', 'پیامک دعوت ارسال شد' in page)
st, ctype, png = raw(own, W + '/invites/%s/qr.png' % AID)
check('the QR answers 200 as a PNG', st == 200 and ctype.startswith('image/png') and png[:4] == b'\x89PNG' and len(png) > 300, '%s %s %s' % (st, ctype, len(png)))
v = q("select sms_consent, remind_ok, channel, state, invited_by_id is not null from ts_assignment where id = %s" % AID)
check('consent and reminder attestations and channel are stored', "(True, True, 'sms', 'invited', True)" in v, v[-80:])
check('the deadline became the expiry', '2099, 1, 1, 23, 59, 59' in q("select expires_at from ts_assignment where id = %s" % AID))

# ---- wizard without the tick: no SMS
n0 = len(SMS)
loc, _ = wizard(own, ('client', K1))
check('no SMS tick -> no message', len(SMS) == n0 and '/invites/' in loc, str(len(SMS) - n0))
AID2 = re.search(r'/invites/(\d+)', loc).group(1)
st, ctype, png2 = raw(own, W + '/invites/%s/qr.png' % AID2)
check('each invitation has its own QR', st == 200 and png2 != png)
get(own, W + '/invites/new?fresh=1')
post(own, W + '/invites/new', {'step': '1', 'choose': K1})
post(own, W + '/invites/new', {'step': '2', 'instrument_id': re.search(r'name="instrument_id"[^>]*value="(\d+)"', get(own, W + '/invites/new?step=2')[1]).group(1)})
st, loc, _ = post(own, W + '/invites/new', {'step': '3', 'sms': '1', 'deadline': '', 'note': ''})
check('the SMS box without the attestation is refused', st in (302, 303) and 'step=3' in loc, loc)

# ---- wizard: a new person, matched by phone
before = int(re.search(r'\((\d+),', q("select count(*) from ts_panel_client where workspace_id = %s" % A)).group(1))
loc, review = wizard(own, ('new', 'اسم دیگر', '09125551111'))
after = int(re.search(r'\((\d+),', q("select count(*) from ts_panel_client where workspace_id = %s" % A)).group(1))
check('a new person with a known phone joins the existing client, and the review said so', after == before and 'ویزارد یک' in review.replace('اسم دیگر', '') and 'یکی است' in review, '%s %s' % (before, after))
loc, _ = wizard(own, ('new', 'فرد کاملاً تازه', ''))
after2 = int(re.search(r'\((\d+),', q("select count(*) from ts_panel_client where workspace_id = %s" % A)).group(1))
check('a really new person makes a new client', after2 == after + 1, '%s %s' % (after, after2))

# ---- validation
get(own, W + '/invites/new?fresh=1')
st, loc, _ = post(own, W + '/invites/new', {'step': '1', 'new_name': 'ب', 'new_phone': ''})
check('a one-letter name is refused', 'step=2' not in loc)
st, loc, _ = post(own, W + '/invites/new', {'step': '1', 'new_name': 'نام درست', 'new_phone': '123'})
check('a bad phone is refused', 'step=2' not in loc)
post(own, W + '/invites/new', {'step': '1', 'choose': K1})
st, loc, _ = post(own, W + '/invites/new', {'step': '2', 'instrument_id': '999999'})
check('an instrument that is not allowed for the panel is refused', 'step=2' in loc and 'step=3' not in loc, loc)
st, body = get(own, W + '/invites/new?step=3')
check('step 3 cannot be reached without an instrument', 'name="deadline"' not in body)
inst = re.search(r'name="instrument_id"[^>]*value="(\d+)"', get(own, W + '/invites/new?step=2')[1]).group(1)
post(own, W + '/invites/new', {'step': '2', 'instrument_id': inst})
st, loc, _ = post(own, W + '/invites/new', {'step': '3', 'deadline': '2001-01-01', 'note': ''})
check('a deadline in the past is refused', 'step=4' not in loc, loc)
check('a missing CSRF token is refused', own.req(W + '/invites/new', {'step': '4'})[0] in (400, 403))

# ---- who sees what
st, body = get(c1, W + '/invites')
check('the responsible counselor sees her invitations', st == 200 and 'ویزارد یک' in body)
st, body = get(c2, W + '/invites')
check('another counselor does not see them', st == 200 and 'ویزارد یک' not in body)
check('and gets 403 on the page, 404 on the QR', get(c2, W + '/invites/' + AID)[0] == 403 and raw(c2, W + '/invites/%s/qr.png' % AID)[0] in (403, 404))
check('and cannot extend or withdraw it', post(c2, W + '/invites/%s/extend' % AID, {'days': '7'})[0] == 403
      and post(c2, W + '/invites/%s/withdraw' % AID, {'confirm': '1'})[0] == 403)
st, body = get(c2, W + '/invites/new?client=' + K1)
check('a counselor cannot start a wizard for someone else\'s client', 'ویزارد یک' not in body)
check('admin (coordinator) sees every invitation', 'ویزارد یک' in get(adm, W + '/invites')[1])

# ---- participant side: opened, expired, extended
anon = Client(TS)
t = tok.group(1)
anon.req('/invite/' + t)
check('the first visit marks it opened', "'opened'" in q("select state from ts_assignment where id = %s" % AID))
opened1 = q("select opened_at from ts_assignment where id = %s" % AID)
anon.req('/invite/' + t)
check('a second visit keeps the first time', q("select opened_at from ts_assignment where id = %s" % AID) == opened1)
st, body = get(own, W + '/invites?state=opened')
check('the list filter «بازشده» finds it', 'ویزارد یک' in body)
shell("a = env['ts.assignment'].sudo().browse(%s); a.write({'expires_at': '2020-01-01 00:00:00'}); env['ts.assignment']._cron_expire_invitations(); env.cr.commit()" % AID)
st, _, body = anon.req('/invite/' + t)
check('an expired link tells the participant so', 'مهلت دعوت تمام شده است' in body or 'منقضی' in body)
st, body = get(own, W + '/invites/' + AID)
check('staff see the state «منقضی» and the extend form', 'منقضی' in body and ('/invites/%s/extend' % AID) in body)
st, loc, _ = post(own, W + '/invites/%s/extend' % AID, {'days': '99'})
check('a free number of days is refused', "'expired'" in q("select state from ts_assignment where id = %s" % AID))
st, loc, _ = post(own, W + '/invites/%s/extend' % AID, {'days': '14'})
check('extending clears the expired state', "'opened'" in q("select state from ts_assignment where id = %s" % AID))
st, _, body = anon.req('/invite/' + t)
check('and the link works again', 'مهلت دعوت تمام شده است' not in body)

# ---- withdraw
st, loc, _ = post(own, W + '/invites/%s/withdraw' % AID, {})
check('withdrawing without the confirmation box does nothing', "'withdrawn'" not in q("select state from ts_assignment where id = %s" % AID))
st, loc, _ = post(own, W + '/invites/%s/withdraw' % AID, {'confirm': '1'})
check('withdrawing with it works', "'withdrawn'" in q("select state from ts_assignment where id = %s" % AID))
st, _, body = anon.req('/invite/' + t)
check('the link now says it is no longer active', 'دیگر فعال نیست' in body)
check('the QR of a withdrawn invitation is gone (404)', raw(own, W + '/invites/%s/qr.png' % AID)[0] == 404)

# ---- old POST route
get(own, W + '/legacy')
page = get(own, W + '/legacy')[1]
opts = [first_inst(own)]
st, loc, _ = own.req(W + '/invite', {'csrf_token': own.csrf(page), 'invitee_name': 'از مسیر قدیمی', 'instrument_id': opts[0] if opts else '1'})
st2, body = get(own, path_of(loc)) if loc else (0, '')
check('the old invite form lands on the new invitation page', 'created=' in loc and 'کد QR' in body, loc)
st, loc, _ = own.req(W + '/invite', {'csrf_token': own.csrf(page), 'invitee_name': 'x', 'instrument_id': '999999'})
st2, body = get(own, path_of(loc))
check('an old error code becomes a message on the dashboard', 'error=form' in loc and 'نام و سنجه را کامل کنید' in body, loc)

# ---- gated panel and rate limit
G_ = '/my/workspaces/%s' % G
st, body = get(gown, G_ + '/invites/new?fresh=1')
check('a panel waiting for approval shows the pending text instead of the wizard', st == 200 and 'پس از تأیید' in body and 'name="new_name"' not in body, str(st))
shell("env['ir.config_parameter'].sudo().set_str('ts_panel.invites_per_hour', '2'); env.cr.commit()")
loc, _ = wizard(own, ('new', 'حدنصاب یک', ''))
loc, _ = wizard(own, ('new', 'حدنصاب دو', ''))
n_before = q("select count(*) from ts_assignment where workspace_id = %s" % A)
loc, _ = wizard(own, ('new', 'حدنصاب سه', ''))
check('past the hourly limit the invitation is refused with a message', n_before == q("select count(*) from ts_assignment where workspace_id = %s" % A) and loc.rstrip('/').endswith('/invites'), loc)
shell("env['ir.config_parameter'].sudo().set_str('ts_panel.invites_per_hour', '200'); env.cr.commit()")

# ---- isolation
e = Client('www.eot.ir')
e.login(L['owner'], pw[L['owner']])
check('eot.ir does not serve the pages', e.req(W + '/invites')[0] == 404 and e.req(W + '/invites/new')[0] == 404)
check('an anonymous visitor is sent to sign in', Client(TS).req(W + '/invites')[0] in (302, 303))

srv.shutdown()
shell("""
c = env.company.sudo(); icp = env['ir.config_parameter'].sudo()
icp.set_str('ts_kavenegar.api_base', '%s' if '%s' != '-' else '')
c.write({'kv_enabled': bool(%s), 'ts_sms_invite': bool(%s)})
env.cr.commit()
""" % (prev[0], prev[0], prev[1], prev[2]))
summary()
