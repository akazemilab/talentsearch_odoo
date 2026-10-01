#!/usr/bin/env python3
"""Talent Search SMS flows over HTTP against a served CLONE, with a LOCAL fake Kavenegar.
    ts_http_sms.py DB PORT
Checks: phone OTP page (send/verify/limits/prefs/remove), invitation SMS with consent,
result-ready SMS without result text, secrets masked in the log, eot.ir isolation."""
import http.server, json, os, re, sys, threading, urllib.parse
FAKE_PORT = 18099 + 10 * int(__import__('os').environ.get('TS_SLOT', '0'))   # one fake Kavenegar per rehearsal slot

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
import importlib.util
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, path_of, shell = lib.Client, lib.check, lib.ensure_user, lib.path_of, lib.shell

REQS = []
MID = [700000]


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
        elif path == 'verify/lookup':
            MID[0] += 1
            ent.append({'messageid': MID[0], 'status': 5, 'statustext': 's', 'receptor': q['receptor'], 'cost': 90})
        out = json.dumps({'return': {'status': 200, 'message': 'ok'}, 'entries': ent}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(out)

    do_GET = do_POST = do_DELETE = _do


srv = http.server.ThreadingHTTPServer(('127.0.0.1', FAKE_PORT), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()

shell("""
env['ir.config_parameter'].sudo().set_str('ts_kavenegar.api_base', 'http://127.0.0.1:@FAKEPORT@/v1/%s/%s.json')
c = env.company.sudo()
c.write({'kv_lines': '10004346'})
c.write({'kv_enabled': True, 'kv_api_key': 'FAKEKEY', 'kv_sender': '10004346', 'ts_sms_invite': True, 'ts_sms_result': True, 'ts_sms_otp': True, 'ts_sms_otp_template_id': False})
env['sms.sms'].search([]).unlink()
env['ts.phone.otp'].sudo().search([]).unlink()
env.cr.commit()
""".replace('@FAKEPORT@', str(FAKE_PORT)))

TS = 'talentsearch.ir'
PART = 'ts.sms.part.http@example.invalid'
pw = ensure_user(PART)
shell("u=env['res.users'].search([('login','=','%s')]); u.partner_id.sudo().write({'ts_phone': False, 'ts_phone_verified_at': False, 'ts_sms_results': False}); env['ts.phone.otp'].sudo().search([('user_id','=',u.id)]).unlink(); env.cr.commit()" % PART)
p = Client(TS)
check('participant login', p.login(PART, pw))
st, _, page = p.req('/my/account')
m = re.search(r'<a[^>]*href="/my/phone"[^>]*>', page)
check('account page links the phone page (S15)', st == 200 and m and 'd-none' not in m.group(0), str(m and m.group(0)[:120]))
st, _, page = p.req('/my/phone')
check('/my/phone 200 with send form', st == 200 and 'ارسال کد تأیید' in page and 'title' in page)
st, loc, _ = p.req('/my/phone/send', {'csrf_token': p.csrf(page), 'phone': '123'})
check('bad number -> format', 'msg=format' in loc, loc)
n0 = len([r for r in REQS if r[0].startswith('sms/send')])
st, loc, _ = p.req('/my/phone/send', {'csrf_token': p.csrf(page), 'phone': '09121112222'})
check('good number -> sent', 'msg=sent' in loc and 'pending=1' in loc, loc)
sent = [r for r in REQS if r[0] == 'sms/send']
check('exactly one SMS to Kavenegar', len(sent) == n0 + 1)
code = re.search(r'(\d{6})', sent[-1][1]['message']).group(1)
check('SMS goes to the given number from default line', sent[-1][1]['receptor'] == '09121112222' and sent[-1][1].get('sender') == '10004346')
st, loc, _ = p.req('/my/phone/send', {'csrf_token': p.csrf(page), 'phone': '09121112222'})
check('immediate resend -> cooldown', 'msg=cooldown' in loc, loc)
wrong = '000000' if code != '000000' else '111111'
st, loc, page2 = p.req('/my/phone?pending=1')
st, loc, _ = p.req('/my/phone/verify', {'csrf_token': p.csrf(page2), 'code': wrong})
check('wrong code -> wrong', 'msg=wrong' in loc, loc)
st, loc, _ = p.req('/my/phone/verify', {'csrf_token': p.csrf(page2), 'code': code})
check('right code -> verified', 'msg=verified' in loc, loc)
st, _, page3 = p.req('/my/phone?msg=verified')
check('page shows masked number, never the full one', '۰۹۱۲***۲۲۲۲' in page3 and '09121112222' not in page3)
out = shell("""
u = env['res.users'].search([('login','=','%s')])
pt = u.partner_id
print('PH', pt.ts_phone, pt.ts_sms_results)
import json
rows = env['kavenegar.message'].search([('receptor','=','09121112222')])
print('LOGBODY', json.dumps(rows.mapped('body'), ensure_ascii=False))
print('OTPROW', env['ts.phone.otp'].sudo().search_count([('user_id','=',u.id)]))
""" % PART)
check('partner stores verified phone + opt-in', 'PH 09121112222 True' in out, out[-200:])
check('OTP masked in Kavenegar log (no code)', 'LOGBODY' in out and code not in out.split('LOGBODY', 1)[1].split('\n')[0], out[-200:])
st, loc, _ = p.req('/my/phone/prefs', {'csrf_token': p.csrf(page3)})
out = shell("u=env['res.users'].search([('login','=','%s')]); print('OPT', u.partner_id.ts_sms_results)" % PART)
check('opt-out saved', 'OPT False' in out, out[-80:])
p.req('/my/phone/prefs', {'csrf_token': p.csrf(page3), 'results': '1'})

# ---- result-ready SMS: no result content, only for opted-in verified users
out = shell("""
u = env['res.users'].search([('login','=','%s')])
inst = env['ts.instrument'].search([('state','=','published'),('audience','=','adult'),('code','!=','TALENT-INV-15')], limit=1)
a = env['ts.attempt'].create({'user_id': u.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id})
a.give_consent(role='self')
for it in a.active_items():
    a.save_answer(it.id, 3)
a.action_submit()
print('STATE', a.state)
env.cr.commit()
""" % PART)
check('attempt submitted', 'STATE done' in out, out[-200:])
res = [r for r in REQS if r[0] == 'sms/send' and 'نتیجهٔ سنجهٔ شما' in r[1].get('message', '')]
check('result-ready SMS sent once', len(res) == 1, str(len(res)))
msg = res[0][1]['message'] if res else ''
check('result SMS has link to /my/assessments and no scores', '/my/assessments' in msg and not re.search(r'نمره|امتیاز|٪|%', msg), msg)

# ---- invitation SMS
HR = 'ts.sms.hr.http@example.invalid'
hr_pw = ensure_user(HR)
out = shell(
    "u=env['res.users'].search([('login','=','%s')])\n"
    "org=env['res.partner'].search([('name','=','سازمان آزمون پیامک')],limit=1) or env['res.partner'].create({'name':'سازمان آزمون پیامک','is_company':True})\n"
    "ws=env['ts.workspace'].search([('name','=','فضای آزمون پیامک')],limit=1) or env['ts.workspace'].create({'approved_on':'2026-01-01 00:00:00','name':'فضای آزمون پیامک','purpose':'employment','partner_id':org.id})\n"
    "ws.state='active'\n"
    "env['ts.workspace.member'].search([('workspace_id','=',ws.id),('user_id','=',u.id)]) or env['ts.workspace.member'].create({'workspace_id':ws.id,'user_id':u.id,'role':'hr_admin'})\n"
    "inst=ws.env['ts.workspace.member'].search([('workspace_id','=',ws.id),('user_id','=',u.id)]).allowed_instruments()[:1]\n"
    "env.cr.commit()\nprint('WS', ws.id, 'INST', inst.id)\n" % HR)
ws_id, inst_id = re.search(r'WS (\d+) INST (\d+)', out).groups()
hr = Client(TS)
check('hr login', hr.login(HR, hr_pw))
st, _, page = hr.req('/my/workspaces/%s/legacy' % ws_id)
check('invite form has phone + consent when SMS enabled', st == 200 and 'name="invitee_phone"' in page and 'name="sms_consent"' in page)
check('old "no SMS" hint replaced', 'تلنت سرچ ایمیل یا پیامک نمی‌فرستد' not in page)
n = len([r for r in REQS if r[0] == 'sms/send'])
st, loc, _ = hr.req('/my/workspaces/%s/invite' % ws_id, {'csrf_token': hr.csrf(page), 'invitee_name': 'علی آزمون', 'instrument_id': inst_id,
                                                       'invitee_phone': '09123334444'})
check('phone without consent -> no SMS', len([r for r in REQS if r[0] == 'sms/send']) == n and 'created=' in loc, loc)
st, loc, _ = hr.req('/my/workspaces/%s/invite' % ws_id, {'csrf_token': hr.csrf(page), 'invitee_name': 'رضا آزمون', 'instrument_id': inst_id,
                                                       'invitee_phone': '+98 912 333 5555', 'sms_consent': '1'})
inv = [r for r in REQS if r[0] == 'sms/send'][n:]
check('consented invite -> exactly one SMS', len(inv) == 1 and inv[0][1]['receptor'] == '09123335555', str(len(inv)))
check('invite SMS carries invite link, no test content', inv and '/invite/' in inv[0][1]['message'] and 'فضای آزمون پیامک' in inv[0][1]['message'])
st, _, page = lib.follow(hr, loc)
check('dashboard confirms SMS sent', 'پیامک دعوت ارسال شد' in page)
st, loc, _ = hr.req('/my/workspaces/%s/invite' % ws_id, {'csrf_token': hr.csrf(page), 'invitee_name': 'بدون پیامک', 'instrument_id': inst_id})
check('invite without phone sends nothing', len([r for r in REQS if r[0] == 'sms/send']) == n + 1)

# ---- disabled Kavenegar: everything is off and says so
shell("c=env.company.sudo(); c.kv_enabled=False; env.cr.commit()")
st, _, page = p.req('/my/phone')
check('disabled: phone page says not active', st == 200 and 'هنوز فعال نشده است' in page and 'ارسال کد تأیید' not in page)
_, _, home = p.req('/my/account')
st, loc, _ = p.req('/my/phone/send', {'csrf_token': p.csrf(home), 'phone': '09121112222'})
check('disabled: send refused', 'msg=disabled' in loc or 'msg=cooldown' in loc, '%s %s' % (st, loc))
st, _, page = hr.req('/my/workspaces/%s/legacy' % ws_id)
check('disabled: invite form keeps old text, no phone field', 'name="invitee_phone"' not in page and 'تلنت سرچ ایمیل یا پیامک نمی‌فرستد' in page)

# ---- eot.ir isolation
e = Client('www.eot.ir')
st, _, _ = e.req('/my/phone')
check('eot.ir /my/phone is not served', st in (404, 302, 303) , str(st))
st, _, page = e.req('/kavenegar/x/status')
check('eot.ir webhook path 404', st == 404, str(st))
shell("env['ir.config_parameter'].sudo().set_str('ts_kavenegar.api_base', ''); env.cr.commit()")
lib.summary()
