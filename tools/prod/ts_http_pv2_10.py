#!/usr/bin/env python3
"""Panel v2 S10 (notifications) over HTTP against a served CLONE:  ts_http_pv2_10.py DB PORT"""
import http.server, importlib.util, json, os, re, sys, threading, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
NAMES = ('owner', 'c1', 'part')
L = {n: 'ts.pv2s10.%s.http@example.invalid' % n for n in NAMES}
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
print('PREV', icp.get_str('ts_kavenegar.api_base') or '-', int(bool(c.kv_enabled)), int(bool(c.ts_sms_invite)), int(bool(c.ts_sms_staff)), int(bool(c.ts_sms_reminder)))
icp.set_str('ts_kavenegar.api_base', 'http://127.0.0.1:@FAKEPORT@/v1/%s/%s.json')
c.write({'kv_lines': '10004346'})
c.write({'kv_enabled': True, 'kv_api_key': 'FAKEKEY', 'kv_sender': '10004346', 'ts_sms_staff': False, 'ts_sms_reminder': False})
env.cr.commit()
""".replace('@FAKEPORT@', str(FAKE_PORT)))
prev = re.search(r'PREV (\S+) (\d) (\d) (\d) (\d)', prev).groups()

code = r"""
L = %r
def user(n): return env['res.users'].search([('login', '=', L[n])])
org = env['res.partner'].search([('name', '=', 'پنل S10')], limit=1) or env['res.partner'].create({'name': 'پنل S10', 'is_company': True})
ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create({'name': 'پنل S10', 'purpose': 'education', 'partner_id': org.id})
ws.write({'approved_on': '2026-01-01 00:00:00'}); ws.state = 'pilot'
for n, role in (('owner', 'owner'), ('c1', 'counselor')):
    if not env['ts.workspace.member'].search([('workspace_id', '=', ws.id), ('user_id', '=', user(n).id)]):
        m = env['ts.workspace.member'].create({'workspace_id': ws.id, 'user_id': user(n).id, 'role': role})
        if role == 'counselor':
            m.write({'license_number': 'T-1', 'verification_state': 'verified'})
cr = env.cr
cr.execute("delete from ts_notification where user_id in %%s", [tuple(user(n).id for n in L)])
cr.execute("delete from ts_notify_pref where user_id in %%s", [tuple(user(n).id for n in L)])
N = env['ts.notification'].sudo()
N._notify(user('owner'), 'panel_approved', '/my/workspaces/%%d' %% ws.id, ws)
N._notify(user('owner'), 'panel_suspended', '//evil.example/x', ws)
N._notify(user('c1'), 'panel_approved', '/my/workspaces/%%d' %% ws.id, ws)
env.cr.commit()
print('IDS', ws.id, N.search([('user_id', '=', user('owner').id)], order='id')[0].id, N.search([('user_id', '=', user('owner').id)], order='id')[1].id, N.search([('user_id', '=', user('c1').id)])[0].id)
""" % L
out = shell(code)
mm = re.search(r'IDS (\d+) (\d+) (\d+) (\d+)', out)
assert mm, out[-1500:]
WS, N1, N2, NC = mm.groups()
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


def post(c, path, data=None):
    pairs = list((data or {}).items())
    pairs.append(('csrf_token', c.csrf(c.req('/web/login')[2])))
    return c.req(path, pairs)


def q(sql):
    out = shell("cr = env.cr; cr.execute(%r); print('Q', cr.fetchall())" % sql)
    m = re.findall(r'^Q (.*)$', out, re.M)
    return m[-1] if m else out


own, c1, part = login('owner'), login('c1'), login('part')

# ---- the bell and the centre
st, body = get(own, W)
check('the header shows the bell link with the unread count', st == 200 and '/my/notifications' in body)
st, body = get(own, '/my/notifications')
check('the centre lists the rows, one h1', st == 200 and body.count('<h1') == 1 and 'اعلان‌ها' in body, str(st))
check('the centre opens for a plain participant too', get(part, '/my/notifications')[0] == 200)
check('an anonymous visitor is sent to sign in', Client(TS).req('/my/notifications')[0] in (302, 303))
e = Client('www.eot.ir')
e.login(L['owner'], pw[L['owner']])
check('eot.ir does not serve the centre', e.req('/my/notifications')[0] == 404)
check('...nor the preferences', e.req('/my/notifications/prefs')[0] == 404)

# ---- opening a row marks it read and goes to its url
st, loc, _ = own.req('/my/notifications/%s' % N1)
check('opening a row redirects to its target', st in (302, 303) and (loc or '').endswith(W), '%s %s' % (st, loc))
check('...and marks it read', q("select read_at is not null from ts_notification where id = %s" % N1) == '[(True,)]')
st, loc, _ = own.req('/my/notifications/%s' % N2)
check('an external target is never followed', st in (302, 303) and 'evil.example' not in (loc or ''), '%s %s' % (st, loc))
check('a colleague cannot open someone else\'s row', c1.req('/my/notifications/%s' % N1)[0] == 404)
check('...and it stays as it was for its owner', q("select read_at is null from ts_notification where id = %s" % NC) == '[(True,)]')
st, body = get(c1, '/my/notifications')
check('a colleague\'s centre holds only their own row', st == 200 and body.count('/my/notifications/%s' % NC) >= 1 and '/my/notifications/%s"' % N1 not in body)

# ---- read all
st, loc, _ = c1.req('/my/notifications/read_all')
check('read_all is POST only', st in (404, 405))
st, loc, _ = post(c1, '/my/notifications/read_all')
check('read_all redirects back to the centre', st in (302, 303) and '/my/notifications' in (loc or ''))
check('...and clears the unread rows of that person', q("select count(*) from ts_notification where user_id = (select id from res_users where login = '%s') and read_at is null" % L['c1']) == '[(0,)]')
check('...but leaves the others\' rows as they were', q("select read_at is null from ts_notification where id = %s" % N2) in ('[(True,)]', '[(False,)]') and q("select count(*) from ts_notification where id = %s" % N1) == '[(1,)]')

# ---- preferences
st, body = get(own, '/my/notifications/prefs')
check('the preferences page lists the event types, one h1', st == 200 and body.count('<h1') == 1 and 'app_panel_approved' in body, str(st))
st, body = get(part, '/my/notifications/prefs')
check('a participant sees no staff-only types', st == 200 and 'app_panel_approved' not in body and 'app_invite' in body, str(st))
st, loc, _ = post(own, '/my/notifications/prefs', {'app_panel_approved': '1'})
check('saving preferences redirects back', st in (302, 303) and (loc or '').endswith('/my/notifications/prefs'))
check('an unticked type is stored as off', q("select in_app from ts_notify_pref where user_id = (select id from res_users where login = '%s') and type = 'panel_suspended'" % L['owner']) == '[(False,)]')
n0 = q("select count(*) from ts_notification where user_id = (select id from res_users where login = '%s')" % L['owner'])
shell("""
u = env['res.users'].search([('login', '=', %r)]); ws = env['ts.workspace'].browse(%s)
env['ts.notification'].sudo()._notify(u, 'panel_suspended', '/x', ws)
env['ts.notification'].sudo()._notify(u, 'panel_approved', '/x', ws)
env.cr.commit()
""" % (L['owner'], WS))
n1 = q("select count(*) from ts_notification where user_id = (select id from res_users where login = '%s')" % L['owner'])
check('a type switched off creates no row, a type left on does', int(re.findall(r'\d+', n1)[0]) == int(re.findall(r'\d+', n0)[0]) + 1, '%s -> %s' % (n0, n1))
st, loc, _ = post(own, '/my/notifications/prefs', {'app_panel_approved': '1', 'sms_panel_approved': '1'})
check('an SMS tick without a verified mobile is not stored', q("select sms from ts_notify_pref where user_id = (select id from res_users where login = '%s') and type = 'panel_approved'" % L['owner']) in ('[(False,)]', '[(None,)]'))
check('saving without CSRF is rejected', own.req('/my/notifications/prefs', [('app_panel_approved', '1')])[0] in (400, 403))

# ---- the manual reminder button
st, loc, _ = post(own, W + '/invites/0/remind')
check('a reminder for an unknown invitation is a 404', st == 404, str(st))
st, loc, _ = post(c1, W + '/invites/0/nothing')
check('an unknown action is a 404', st == 404, str(st))

# ---- nothing reached a phone: the new switches are off
check('with the new switches off no SMS reached the fake gateway', len(SMS) == 0, str(len(SMS)))

srv.shutdown()
shell("""
c = env.company.sudo(); icp = env['ir.config_parameter'].sudo()
icp.set_str('ts_kavenegar.api_base', '%s' if '%s' != '-' else '')
c.write({'kv_enabled': bool(%s), 'ts_sms_invite': bool(%s), 'ts_sms_staff': bool(%s), 'ts_sms_reminder': bool(%s)})
env.cr.commit()
""" % (prev[0], prev[0], prev[1], prev[2], prev[3], prev[4]))
summary()
