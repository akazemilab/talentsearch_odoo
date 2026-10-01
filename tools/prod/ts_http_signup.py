#!/usr/bin/env python3
"""Mobile sign-in/sign-up + invite links over HTTP against a served CLONE with a LOCAL fake Kavenegar:
    ts_http_signup.py DB PORT"""
import http.server, json, os, re, sys, threading, urllib.parse
FAKE_PORT = 18098 + 10 * int(__import__('os').environ.get('TS_SLOT', '0'))   # one fake Kavenegar per rehearsal slot

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
import importlib.util
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, summary, shell = lib.Client, lib.check, lib.summary, lib.shell
REQS, MID = [], [800000]


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _do(self):
        n = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(n).decode() if n else ''
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
        q.update(dict(urllib.parse.parse_qsl(body)))
        path = urllib.parse.urlsplit(self.path).path.split('/v1/', 1)[1].split('/', 1)[1][:-5]
        REQS.append((path, q))
        ent = []
        if path == 'sms/send':
            for r in q['receptor'].split(','):
                MID[0] += 1
                ent.append({'messageid': MID[0], 'message': q['message'], 'status': 1, 'statustext': 'q', 'sender': '10004346', 'receptor': r, 'cost': 100})
        out = json.dumps({'return': {'status': 200, 'message': 'ok'}, 'entries': ent}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(out)

    do_GET = do_POST = do_DELETE = _do


srv = http.server.ThreadingHTTPServer(('127.0.0.1', FAKE_PORT), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
PHONE, NAME = '09127770001', 'ثبت‌نام‌کنندهٔ HTTP'
out = shell("""
env['ir.config_parameter'].sudo().set_str('ts_kavenegar.api_base', 'http://127.0.0.1:@FAKEPORT@/v1/%s/%s.json')
c = env.company.sudo()
c.write({'kv_lines': '10004346'})
c.write({'kv_enabled': True, 'kv_api_key': 'FAKEKEY', 'kv_sender': '10004346', 'ts_sms_otp': True, 'ts_sms_otp_template_id': False})
env['ts.signup.otp'].sudo().search([]).unlink()
for u in env['res.users'].sudo().search([('login', '=', '@PHONE@')]):
    u.partner_id.sudo().write({'ts_phone': False}); u.sudo().write({'active': False, 'login': 'old.' + str(u.id)})
inst = env['ts.instrument'].search([('state', '=', 'published'), ('purpose', '=', 'employment')], limit=1)
org = env['res.partner'].search([('name', '=', 'سازمان ثبت‌نام HTTP')], limit=1) or env['res.partner'].create({'name': 'سازمان ثبت‌نام HTTP', 'is_company': True})
ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create({'approved_on': '2026-01-01 00:00:00', 'name': 'سازمان ثبت‌نام HTTP', 'purpose': 'employment', 'partner_id': org.id})
ws.state = 'active'
A = env['ts.assignment']
a = A.create({'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': 'دعوت‌شدهٔ HTTP'})
old = A.create({'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': 'دعوت قدیمی HTTP'})
env.cr.execute("update ts_assignment set create_date = now() - interval '40 days', expires_at = now() - interval '10 days' where id = %s", [old.id])
env.cr.commit()
print('TOK', a.token, old.token)
""".replace('@FAKEPORT@', str(FAKE_PORT)).replace('@PHONE@', PHONE))
tok, tok_old = re.search(r'TOK (\S+) (\S+)', out).groups()
TS = 'talentsearch.ir'


def last_code():
    for path, q in reversed(REQS):
        if path == 'sms/send':
            m = re.search(r'(\d{6})', q.get('message', ''))
            if m:
                return m.group(1)


def bypass_cooldown():
    shell("env.cr.execute(\"update ts_signup_otp set create_date = create_date - interval '2 minutes'\"); env.cr.commit()")


c = Client(TS)
st, _, page = c.req('/signup')
check('signup page 200 with phone field', st == 200 and 'name="phone"' in page and 'ورود یا ثبت‌نام با موبایل' in page, str(st))
st, _, _ = Client('www.eot.ir').req('/signup')
check('eot.ir has no /signup', st == 404, str(st))
st, loc, _ = c.req('/signup/send', {'csrf_token': c.csrf(page), 'phone': '123', 'next': '/my'})
check('bad number -> format', 'msg=format' in loc, loc)
st, loc, _ = c.req('/signup/send', {'csrf_token': c.csrf(page), 'phone': PHONE, 'next': '//evil.example/x'})
check('good number -> code step, hostile next sanitised', 'step=code' in loc and 'evil' not in loc and 'next=/my' in loc, loc)
st, _, page = c.req('/signup?step=code&next=/my')
check('code step page', st == 200 and 'name="code"' in page)
code = last_code()
check('a six-digit code was sent through the (fake) Kavenegar', bool(code))
st, loc, _ = c.req('/signup/verify', {'csrf_token': c.csrf(page), 'code': '000000' if code != '000000' else '111111', 'next': '/my'})
check('wrong code -> msg=wrong', 'msg=wrong' in loc, loc)
st, loc, _ = c.req('/signup/verify', {'csrf_token': c.csrf(page), 'code': code, 'next': '/my'})
check('right code from a new number -> name step (no account yet)', 'step=name' in loc, loc)
st, _, page = c.req('/signup?step=name&next=/my')
check('name step page', st == 200 and 'name="name"' in page)
st, loc, _ = c.req('/signup/name', {'csrf_token': c.csrf(page), 'name': 'ا', 'next': '/my'})
check('one-letter name refused', 'msg=noname' in loc, loc)
st, loc, _ = c.req('/signup/name', {'csrf_token': c.csrf(page), 'name': NAME, 'next': '/my'})
check('name submitted -> account created and signed in', st in (302, 303), '%s %s' % (st, loc))
st, _, page = c.req('/my')
check('/my is signed in', st == 200 and NAME in page, str(st))
info = shell("u=env['res.users'].search([('login','=','%s')]); print('U', len(u), u.partner_id.ts_phone, u.share, bool(u.partner_id.ts_phone_verified_at), u.partner_id.ts_sms_results, env['ts.audit.event'].search_count([('event_type','=','account.signup_phone')]))" % PHONE)
check('portal user with verified phone, SMS-results opt-in off, audit written', re.search(r"U 1 %s True True False [1-9]" % PHONE, info) is not None, info.strip()[-80:])
st, loc, _ = c.req('/signup')
check('signed-in visitor is sent on', st in (302, 303), str(st))

# returning user: same number signs straight in
bypass_cooldown()
c2 = Client(TS)
st, _, page = c2.req('/signup')
c2.req('/signup/send', {'csrf_token': c2.csrf(page), 'phone': PHONE, 'next': '/invite/%s' % tok})
code = last_code()
st, _, page = c2.req('/signup?step=code&next=/invite/%s' % tok)
st, loc, _ = c2.req('/signup/verify', {'csrf_token': c2.csrf(page), 'code': code, 'next': '/invite/%s' % tok})
check('returning number signs in directly and lands on the invite', st in (302, 303) and loc.endswith('/invite/%s' % tok), loc)
n = shell("print('N', env['res.users'].search_count([('login','=','%s')]))" % PHONE)
check('no duplicate account for the same number', 'N 1' in n, n.strip()[-10:])
st, _, page = c2.req('/invite/%s' % tok)
check('invite page offers accept to the signed-in user', st == 200 and '/accept' in page and 'اجازه می‌دهم' in page, str(st))
st, loc, _ = c2.req('/invite/%s/accept' % tok, {'csrf_token': c2.csrf(page), 'share': '1'})
check('accepting the invite leads to the test', st in (302, 303) and '/take/' in loc, loc)

# public visitor on an invite: phone sign-in offered; expired link explains itself
c3 = Client(TS)
st, _, page = c3.req('/invite/%s' % tok_old)
check('expired invite explains itself (200, no accept button)', st == 200 and 'منقضی' in page and '/accept' not in page, str(st))
st, _, page = c3.req('/invite/%s' % tok)
check('used invite tells a stranger it is used', st == 200 and 'قبلاً استفاده' in page and '/accept' not in page)
a2 = shell("""
ws = env['ts.workspace'].search([('name','=','سازمان ثبت‌نام HTTP')], limit=1)
a = env['ts.assignment'].create({'workspace_id': ws.id, 'instrument_id': env['ts.instrument'].search([('state','=','published'),('purpose','=','employment')], limit=1).id, 'invitee_name': 'تازه HTTP'})
env.cr.commit(); print('TOK2', a.token)
""")
tok2 = re.search(r'TOK2 (\S+)', a2).group(1)
st, _, page = c3.req('/invite/%s' % tok2)
check('fresh invite offers mobile sign-in with next=/invite/…', st == 200 and '/signup?next=/invite/%s' % tok2 in page and 'ورود یا ثبت‌نام با موبایل' in page, str(st))
# rate limit through the real endpoint
for i in range(6):
    bypass_cooldown()
    st, _, page = c3.req('/signup')
    st, loc, _ = c3.req('/signup/send', {'csrf_token': c3.csrf(page), 'phone': '09127770999', 'next': '/my'})
check('sixth request for one number in an hour is limited', 'msg=limit' in loc, loc)
summary()
