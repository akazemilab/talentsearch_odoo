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
path_of = lib.path_of
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
ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create({'name': 'سازمان ثبت‌نام HTTP', 'purpose': 'employment', 'partner_id': org.id})
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
check('signup page 200 with phone field (S-AUTH, onb1)', st == 200 and 'name="phone"' in page and 'ورود یا ثبت‌نام' in page
      and 'autocomplete="tel"' in page and 'inputmode="numeric"' in page, str(st))
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
check('right code from a new number -> account made at once, no name step (onb1)', st in (302, 303) and loc.endswith('/my') and 'step=name' not in loc, loc)
st, _, page = c.req('/my/account')
check('/my/account is signed in and does not show the number as a name', st == 200 and 'id="acc-name"' in page
      and '0912 777 0001' not in page, str(st))
info = shell("u=env['res.users'].search([('login','=','%s')]); print('U', len(u), u.partner_id.ts_phone, u.share, bool(u.partner_id.ts_phone_verified_at), u.partner_id.ts_sms_results, u.partner_id.ts_name_unknown, env['ts.audit.event'].search_count([('event_type','=','account.signup_phone')]))" % PHONE)
check('portal user with verified phone, name unknown, SMS-results opt-in off, audit written', re.search(r"U 1 %s True True False True [1-9]" % PHONE, info) is not None, info.strip()[-80:])
st, loc, _ = c.req('/my/account/name', {'csrf_token': c.csrf(page), 'name': NAME})
info = shell("u=env['res.users'].search([('login','=','%s')]); print('K', u.name == %r, u.partner_id.ts_name_unknown)" % (PHONE, NAME))
check('a name given on the account page ends «name unknown»', 'K True False' in info, info.strip()[-40:])
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
check('expired invite explains itself (200, no accept button) with a next step', st == 200 and 'مهلت این دعوت تمام شده' in page
      and '/accept' not in page and 'id="ts-state-card"' in page, str(st))
# UX T7 X1: an invitation bound to an account reads like an unknown token to anyone else (same 404, same text): the page
# explains and offers sign-in with the invited number, and returns to the link afterwards
st, _, page = c3.req('/invite/%s' % tok)
# onb2: a visitor who is not signed in may be the invited person on another browser: «ادامه», then a code or the sign-in
check('a used invite opened by a visitor who is not signed in offers «ادامه» only (no consent form, no share tick)',
      st == 200 and '>ادامه<' in page and 'name="share"' not in page and 'موافقم و شروع می‌کنم' not in page)
st_u, _, page_u = c3.req('/invite/%s' % ('f' * 32))
check('...and never the invitee name; an unknown invite token gets the explained 404 (sign-in back to the link)',
      'دعوت‌شدهٔ HTTP' not in page and st_u == 404 and 'این لینک باز نمی‌شود' in page_u and 'id="ts-link-404"' in page_u
      and ('/signup?next=/invite/%s' % ('f' * 32)) in page_u, str(st_u))
a2 = shell("""
ws = env['ts.workspace'].search([('name','=','سازمان ثبت‌نام HTTP')], limit=1)
a = env['ts.assignment'].create({'workspace_id': ws.id, 'instrument_id': env['ts.instrument'].search([('state','=','published'),('purpose','=','employment')], limit=1).id, 'invitee_name': 'تازه HTTP'})
env.cr.commit(); print('TOK2', a.token)
""")
tok2 = re.search(r'TOK2 (\S+)', a2).group(1)
st, _, page = c3.req('/invite/%s' % tok2)
check('fresh invite: the one-tap welcome screen', st == 200 and 'موافقم و شروع می‌کنم' in page, str(st))
check('the welcome states size and time from data first (UX T7 X2: effort_facts)', 'tso-facts' in page and 'دقیقه' in page, str(st))
st, loc, _ = c3.req('/invite/%s/accept' % tok2, {'csrf_token': c3.csrf(page), 'welcome': '1', 'share': '1'})
check('...a link without a number: the tap leads to the mobile sign-in with next=/invite/…', st in (302, 303)
      and path_of(loc) == '/signup?next=/invite/%s' % tok2, loc)
st, _, page = c3.req('/signup?next=/invite/%s' % tok2)
check('the sign-in page reached from an open invite says who invites to what (P2-1)', st == 200 and 'شما را به' in page
      and 'دعوت کرده است' in page, str(st))
st, _, page = c3.req('/signup?next=/invite/%s' % tok)
check('...but not for an invite bound to an account (nothing new disclosed)', st == 200 and 'دعوت کرده است' not in page
      and 'برای پاسخ‌دادن به دعوت' in page, str(st))
# rate limit through the real endpoint
for i in range(6):
    bypass_cooldown()
    st, _, page = c3.req('/signup')
    st, loc, _ = c3.req('/signup/send', {'csrf_token': c3.csrf(page), 'phone': '09127770999', 'next': '/my'})
check('sixth request for one number in an hour is limited', 'msg=limit' in loc, loc)
summary()
