#!/usr/bin/env python3
"""Panel v2 S7 (campaigns) over HTTP against a served CLONE:  ts_http_pv2_7.py DB PORT"""
import http.server, importlib.util, json, os, re, sys, threading, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
NAMES = ('owner', 'admin', 'c1', 'c2', 'gowner', 'p1', 'p2', 'p3')
L = {n: 'ts.pv2s7.%s.http@example.invalid' % n for n in NAMES}
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
A = panel('پنل S7 آموزشی', 'education'); G = panel('پنل S7 کاری در انتظار', 'employment', approved=False)
mo = member(A, 'owner', 'owner'); member(A, 'admin', 'admin'); m1 = member(A, 'c1', 'counselor'); m2 = member(A, 'c2', 'counselor')
member(G, 'gowner', 'owner')
C = env['ts.panel.client']; AS = env['ts.assignment'].sudo(); K = env['ts.campaign'].sudo(); GR = env['ts.panel.group']
cr = env.cr; ws2 = (A.id, G.id)
cr.execute("delete from ts_assignment where workspace_id in %%s", [ws2])
cr.execute("delete from ts_campaign_group_rel where campaign_id in (select id from ts_campaign where workspace_id in %%s)", [ws2])
cr.execute("delete from ts_campaign where workspace_id in %%s", [ws2])
cr.execute("delete from ts_panel_client_group_rel where client_id in (select id from ts_panel_client where workspace_id = %%s and source = 'open_link')", [A.id])
cr.execute("delete from ts_panel_client where workspace_id = %%s and source = 'open_link'", [A.id])
env.invalidate_all()
env.cr.execute("delete from ts_audit_event where event_type = 'campaign.join_try'")
for n, r, ph in (('ویزارد یک', m1, False), ('ویزارد دو', m2, False), ('ویزارد سه', mo, '09125552222')):
    c = C.search([('workspace_id', '=', A.id), ('name', '=', n)], limit=1) or C.create({'workspace_id': A.id, 'name': n, 'responsible_id': r.id})
    c.write({'phone': ph or False, 'responsible_id': r.id, 'state': 'active'})
cid = lambda n: C.search([('workspace_id', '=', A.id), ('name', '=', n)], limit=1)
g1 = GR.search([('workspace_id', '=', A.id), ('name', '=', 'کلاس S7')], limit=1) or GR.create({'workspace_id': A.id, 'name': 'کلاس S7'})
g1.client_ids = [(6, 0, (cid('ویزارد یک') | cid('ویزارد دو')).ids)]
g2 = GR.search([('workspace_id', '=', A.id), ('name', '=', 'پیامک S7')], limit=1) or GR.create({'workspace_id': A.id, 'name': 'پیامک S7'})
g2.client_ids = [(6, 0, cid('ویزارد سه').ids)]
env['ir.config_parameter'].sudo().set_str('ts_panel.invites_per_hour', '200')
env['ir.config_parameter'].sudo().set_str('ts_panel.join_per_hour_ip', '30')
env.cr.commit()
print('IDS', A.id, G.id, g1.id, g2.id)
""" % L
out = shell(code)
mm = re.search(r'IDS (\d+) (\d+) (\d+) (\d+)', out)
assert mm, out[-1500:]
A, G, G1, G2 = mm.groups()
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
gown, p1, p2, p3 = login('gowner'), login('p1'), login('p2'), login('p3')
inst_id = re.search(r'name="instrument_id"[^>]*value="(\d+)"', get(own, W + '/campaigns/new')[1]).group(1)


def count(table_where):
    return q('select count(*) from ' + table_where)


# ---- list, menu, form
st, body = get(own, W + '/campaigns')
check('the campaign list opens with its empty text', st == 200 and 'برای دعوت یک کلاس یا گروه' in body and body.count('<h1') == 1, str(st))
check('the menu has the campaigns item', W + '/campaigns' in get(own, W)[1])
st, body = get(own, W + '/campaigns/new?group=%s' % G1)
check('the form opens prefilled from a group', st == 200 and 'کلاس S7' in body and 'name="instrument_id"' in body, str(st))
st, body = get(own, W + '/groups/%s' % G1)
check('the group page offers «دعوت گروه»', 'campaigns/new?group=%s' % G1 in body)

# ---- review creates nothing, create makes one invitation per client
n0 = count('ts_assignment where workspace_id = %s' % A)
form = [('kind', 'list'), ('name', 'دعوت هفتم'), ('instrument_id', inst_id), ('group_ids', G1), ('deadline', ''), ('note', 'یادداشت S7'), ('step', 'review')]
st, loc, body = post(own, W + '/campaigns/new', form)
check('review shows who will be invited and creates nothing', st == 200 and 'دعوت می‌شوند' in body and count('ts_assignment where workspace_id = %s' % A) == n0, str(st))
st, loc, _ = post(own, W + '/campaigns/new', [('step', 'create')])
check('create redirects to the campaign page', st in (302, 303) and re.search(r'/campaigns/\d+$', loc or ''), loc)
camp = re.search(r'/campaigns/(\d+)', loc).group(1)
st, body = get(own, W + '/campaigns/%s' % camp)
check('the campaign page lists both invitations with counts', st == 200 and 'ویزارد یک' in body and 'ویزارد دو' in body and 'دعوت ساخته شد' in body, str(st))
check('both invitations carry the campaign and the note', count('ts_assignment where campaign_id = %s and note = %s' % (camp, "'یادداشت S7'")) == '[(2,)]',
      count('ts_assignment where campaign_id = %s' % camp))
st, ct, png = raw(own, W + '/campaigns/%s/sheet' % camp)
check('the print sheet opens', st == 200 and b'invites/' in png)
inv = re.search(r'invites/(\d+)/qr\.png', png.decode('utf-8', 'ignore'))
st, ct, png = raw(own, W + '/invites/%s/qr.png' % inv.group(1)) if inv else (0, '', b'')
check('the sheet QR of an invitation is a PNG', st == 200 and png[:8] == b'\x89PNG\r\n\x1a\n')

# ---- the same group again: everyone already has an open invitation
st, loc, body = post(own, W + '/campaigns/new', form)
check('a second launch for the same group shows nobody left', st == 200 and 'کسی برای دعوت نمانده است' in body and 'دعوت باز برای همین سنجه دارند' in body, str(st))

# ---- colleague's campaign: 403; own scope: a counselor sees only own clients
st, body = get(c1, W + '/campaigns/%s' % camp)
check('a counselor cannot open a colleague\'s campaign', st == 403, str(st))
st, body = get(c1, W + '/campaigns')
check('a counselor\'s list does not show it', st == 200 and 'دعوت هفتم' not in body, str(st))
st, loc, body = post(c1, W + '/campaigns/new', [('kind', 'list'), ('name', 'کلاس من'), ('instrument_id', inst_id), ('group_ids', G1), ('step', 'review')])
check('a counselor reviewing the same group sees only the clients of their own', st == 200 and 'ویزارد دو' not in body, str(st))
check('the QR and the sheet of a colleague\'s campaign are refused', get(c1, W + '/campaigns/%s/sheet' % camp)[0] == 403)

# ---- sms
SMS.clear()
bad = [('kind', 'list'), ('name', 'پیامکی'), ('instrument_id', inst_id), ('group_ids', G2), ('sms', '1'), ('step', 'review')]
st, loc, _ = post(own, W + '/campaigns/new', bad)
check('SMS without the attestation is refused with a message', st in (302, 303) and 'keep=1' in (loc or ''), loc)
ok = bad + [('attest', '1'), ('remind', '1')]
st, loc, body = post(own, W + '/campaigns/new', ok)
st, loc, _ = post(own, W + '/campaigns/new', [('step', 'create')])
check('SMS campaign sent exactly one message to the one client with a phone', len(SMS) == 1 and '/invite/' in SMS[0]['message'] and SMS[0]['receptor'] == '09125552222', str(SMS)[:200])
check('the invitation records the consent and the sms channel', count("ts_assignment where workspace_id = %s and sms_consent and remind_ok and channel = 'sms'" % A) == '[(1,)]')

# ---- gated panel
for path in ('/campaigns', '/campaigns/new'):
    st, body = get(gown, '/my/workspaces/%s%s' % (G, path))
    check('a panel waiting for approval shows the pending text on ' + path, st == 200 and 'پس از تأیید' in body, str(st))

# ---- open link
st, loc, body = post(own, W + '/campaigns/new', [('kind', 'open_link'), ('name', 'پیوند کلاس'), ('instrument_id', inst_id), ('open_max', '2'),
                                                  ('open_days', '14'), ('step', 'review')])
check('review of an open link shows the cap', st == 200 and 'سقف پیوستن' in body, str(st))
st, loc, _ = post(own, W + '/campaigns/new', [('step', 'create')])
oc = re.search(r'/campaigns/(\d+)', loc or '').group(1)
st, body = get(own, W + '/campaigns/%s' % oc)
tok = re.search(r'/c/([0-9a-f]{32})', body)
check('the campaign page shows the open link, the QR and the count', st == 200 and tok and 'campaigns/%s/qr.png' % oc in body and 'از ۲' in body, str(st))
tok = tok.group(1)
st, ct, png = raw(own, W + '/campaigns/%s/qr.png' % oc)
check('the open-link QR is a PNG', st == 200 and png[:8] == b'\x89PNG\r\n\x1a\n')

# ---- the public page
anon = Client(TS)
st, body = get(anon, '/c/' + tok)
check('anonymous: the page offers sign-in with a return path and no form', st == 200 and '/web/login?redirect=/c/' + tok in body and 'name="name"' not in body, str(st))
check('an unknown token is 404', Client(TS).req('/c/' + '0' * 32)[0] == 404)
e = Client('www.eot.ir')
e.login(L['owner'], pw[L['owner']])
check('eot.ir does not serve the open link', e.req('/c/' + tok)[0] == 404)
st, body = get(p1, '/c/' + tok)
check('signed in: the page asks for a name', st == 200 and 'name="name"' in body, str(st))
st, loc, _ = post(p1, '/c/%s/join' % tok, {'name': 'شرکت‌کنندهٔ یک'})
check('joining leads to the ordinary invitation page', st in (302, 303) and '/invite/' in (loc or ''), loc)
inv1 = loc
st, body = get(p1, path_of(loc))
check('the invitation page offers the accept button', st == 200 and '/accept' in body and 'شرکت‌کنندهٔ یک' in body, str(st))
check('a client of the open_link source was created for the account', count("ts_panel_client where workspace_id = %s and source = 'open_link'" % A) == '[(1,)]')
st, loc, _ = post(p1, '/c/%s/join' % tok, {'name': 'شرکت‌کنندهٔ یک'})
check('joining twice returns the same invitation', loc == inv1, str(loc))
st, loc, _ = post(p2, '/c/%s/join' % tok, {'name': 'شرکت‌کنندهٔ دو'})
check('the second person joins', st in (302, 303) and '/invite/' in (loc or ''), loc)
st, loc, _ = post(p3, '/c/%s/join' % tok, {'name': 'شرکت‌کنندهٔ سه'})
check('at the cap the third is sent back to the page', st in (302, 303) and (loc or '').endswith('/c/' + tok), loc)
st, body = get(p3, '/c/' + tok)
check('the page says the capacity is full', st == 200 and 'ظرفیت این دعوت تکمیل شده است' in body and 'name="name"' not in body, str(st))
check('no third invitation exists', count('ts_assignment where campaign_id = %s' % oc) == '[(2,)]')
st, body = get(own, W + '/campaigns/%s' % oc)
check('the owner sees two joined and the full notice', 'ظرفیت تکمیل شد' in body and 'شرکت‌کنندهٔ یک' in body and 'شرکت‌کنندهٔ دو' in body, str(st))
st, ct, png = raw(own, W + '/campaigns/%s/qr.png' % oc)
check('a full link has no QR any more', st == 404)

# ---- expiry and closing
shell("env['ts.campaign'].browse(%s).write({'open_max': 10}); env.cr.commit()" % oc)
shell("env.cr.execute(\"update ts_campaign set open_expires_at = now() - interval '1 hour' where id = %s\"); env.cr.commit()" % oc)
st, body = get(p3, '/c/' + tok)
check('an expired link says so', 'مهلت این دعوت به پایان رسیده است' in body and 'name="name"' not in body)
shell("env.cr.execute(\"update ts_campaign set open_expires_at = now() + interval '1 day' where id = %s\"); env.cr.commit()" % oc)
st, loc, _ = post(own, W + '/campaigns/%s/close' % oc, {})
st, body = get(own, W + '/campaigns/%s' % oc)
check('closing without the tick is refused with a message', 'تأیید را تیک بزنید' in body and count("ts_campaign where id = %s and state = 'closed'" % oc) == '[(0,)]')
st, loc, _ = post(own, W + '/campaigns/%s/close' % oc, {'confirm': '1'})
check('closing with the tick closes the campaign', count("ts_campaign where id = %s and state = 'closed'" % oc) == '[(1,)]')
st, body = get(p3, '/c/' + tok)
check('a closed link says so', 'این دعوت بسته شده است' in body)
st, body = get(p1, path_of(inv1))
check('a person who already joined can still open the invitation', st == 200 and '/accept' in body)
check('closing withdrew nothing', count('ts_assignment where campaign_id = %s and withdrawn is not true' % oc) == '[(2,)]')
check('the audit has the create, join and close events', count("ts_audit_event where event_type in ('campaign.create','campaign.join','campaign.close') and workspace_id = %s" % A) not in ('[(0,)]', '[(1,)]'))

# ---- rate limit per IP hash
st, loc, body = post(own, W + '/campaigns/new', [('kind', 'open_link'), ('name', 'حد'), ('instrument_id', inst_id), ('open_max', '5'), ('open_days', '7'), ('step', 'review')])
st, loc, _ = post(own, W + '/campaigns/new', [('step', 'create')])
oc2 = re.search(r'/campaigns/(\d+)', loc or '').group(1)
tok2 = re.search(r'/c/([0-9a-f]{32})', get(own, W + '/campaigns/%s' % oc2)[1]).group(1)
shell("env['ir.config_parameter'].sudo().set_str('ts_panel.join_per_hour_ip', '1'); env.cr.commit()")
post(p3, '/c/%s/join' % tok2, {'name': 'نخستین تلاش'})
st, loc, _ = post(p3, '/c/%s/join' % tok2, {'name': 'تلاش دوم'})
st, body = get(p3, '/c/' + tok2)
check('past the per-IP limit the join is refused with a message', 'تلاش‌های پیاپی' in body, str(st))
shell("env['ir.config_parameter'].sudo().set_str('ts_panel.join_per_hour_ip', '30'); env.cr.commit()")

# ---- isolation
check('eot.ir does not serve the pages', e.req(W + '/campaigns')[0] == 404 and e.req(W + '/campaigns/new')[0] == 404)
check('an anonymous visitor is sent to sign in', Client(TS).req(W + '/campaigns')[0] in (302, 303))
check('a campaign id of another panel is 404', own.req('/my/workspaces/%s/campaigns/%s' % (A, 999999))[0] == 404)

srv.shutdown()
shell("""
c = env.company.sudo(); icp = env['ir.config_parameter'].sudo()
icp.set_str('ts_kavenegar.api_base', '%s' if '%s' != '-' else '')
c.write({'kv_enabled': bool(%s), 'ts_sms_invite': bool(%s)})
env.cr.commit()
""" % (prev[0], prev[0], prev[1], prev[2]))
summary()
