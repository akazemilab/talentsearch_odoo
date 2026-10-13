#!/usr/bin/env python3
"""onb1 over HTTP against a served CLONE with a LOCAL fake Kavenegar (no SMS or e-mail leaves the machine):
S-AUTH (one mobile sign-in, two states without reload, WebOTP line, 30-day vs browser-session cookie, staff numbers, lock,
help after resends, /my/phone, the once-offer to link a mobile), names (no name step: panel creation and invitations ask
for it), and the panel side (no approval, the first-week invite limit on an HR position, suspend, the licence badge).
eot.ir must stay exactly as it was.
    ts_http_onb1.py DB PORT"""
import http.server, importlib.util, json, os, re, sys, threading, urllib.error, urllib.parse, urllib.request

FAKE_PORT = 18094 + 10 * int(os.environ.get('TS_SLOT', '0'))   # one fake Kavenegar per rehearsal slot
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, summary, shell, ensure_user, path_of = lib.Client, lib.check, lib.summary, lib.shell, lib.ensure_user, lib.path_of
TS, EOT = 'talentsearch.ir', 'www.eot.ir'
REQS, MID = [], [900000]


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
                ent.append({'messageid': MID[0], 'message': q['message'], 'status': 1, 'statustext': 'q', 'sender': '10004346',
                            'receptor': r, 'cost': 100})
        out = json.dumps({'return': {'status': 200, 'message': 'ok'}, 'entries': ent}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(out)

    do_GET = do_POST = do_DELETE = _do


srv = http.server.ThreadingHTTPServer(('127.0.0.1', FAKE_PORT), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()

FA = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')
PH = {'new': '09127778801', 'new2': '09127778802', 'staff': '09127778803', 'lock': '09127778804', 'help': '09127778805',
      'mail': '09127778806'}
L = {n: 'ts.onb1.%s.http@example.invalid' % n for n in ('own', 'mail', 'part', 'cl')}
pw = {u: ensure_user(u) for u in L.values()}
INVITEE = 'داوطلب نام‌دار onb1'

out = shell(r"""
L, PH, INVITEE = %r, %r, %r
from odoo import fields
def user(n): return env['res.users'].search([('login', '=', L[n])])
env['ir.config_parameter'].sudo().set_str('ts_kavenegar.api_base', 'http://127.0.0.1:%d/v1/%%s/%%s.json')
c = env.company.sudo()
c.write({'kv_lines': '10004346'})
c.write({'kv_enabled': True, 'kv_api_key': 'FAKEKEY', 'kv_sender': '10004346', 'ts_sms_otp': True, 'ts_sms_otp_template_id': False})
env['ir.config_parameter'].sudo().set_str('ts_panel.new_panel_daily_invites', '50')
env['ir.config_parameter'].sudo().set_str('ts_panel.invites_per_hour', '200')
phones = list(PH.values())
U = env['res.users'].with_context(active_test=False)
for ph in phones:
    if ph == PH['staff']:
        continue
    for u in U.search([('login', '=', ph)]):
        u.partner_id.sudo().write({'ts_phone': False, 'ts_phone_verified_at': False})
        u.sudo().write({'active': False, 'login': 'old.onb1.%%d' %% u.id})
env['res.partner'].with_context(active_test=False).search([('ts_phone', 'in', [p for p in phones if p != PH['staff']])]).write(
    {'ts_phone': False, 'ts_phone_verified_at': False})
env['ts.signup.otp'].sudo().search([('phone', 'in', phones)]).unlink()
env['ts.signup.lock'].sudo().search([('phone', 'in', phones)]).unlink()
env['ts.phone.otp'].sudo().search(['|', ('phone', 'in', phones), ('user_id', '=', user('mail').id)]).unlink()
env.cr.execute("update ts_signup_otp set create_date = create_date - interval '2 hours'")   # the per-IP hourly window
# a staff (internal) account that holds a verified mobile
st = U.search([('login', '=', 'ts.onb1.staff.http@example.invalid')]) or U.with_context(no_reset_password=True).create(
    {'name': 'کارمند آزمون onb1', 'login': 'ts.onb1.staff.http@example.invalid', 'group_ids': [(6, 0, [env.ref('base.group_user').id])]})
st.write({'active': True})
st.partner_id.write({'ts_phone': PH['staff'], 'ts_phone_verified_at': fields.Datetime.now()})
# the e-mail account: no mobile yet, the offer not shown yet
user('mail').partner_id.write({'ts_phone': False, 'ts_phone_verified_at': False, 'ts_phone_offer_seen': False})
W, M, A = env['ts.workspace'], env['ts.workspace.member'], env['ts.assignment']
emp = env['ts.instrument'].search([('state', '=', 'published'), ('purpose', '=', 'employment')], limit=1)
edu = env['ts.instrument'].search([('code', '=', 'TALENT-INV-15')], limit=1)
# 1. a self-service organization panel (made like a visitor makes it) with an open HR position
org = W.search([('name', '=', 'سازمان onb1 وب')], limit=1) or W.ts_panel_create(user('own'), 'سازمان onb1 وب', 'org', terms=True)
org.write({'state': 'active'})
occ = env['ts.onet.occupation'].search([], limit=1)
P = env['ts.hire.position'].sudo()
P.search([('workspace_id', '=', org.id)]).write({'state': 'closed'})
pos = P.create({'name': 'کارشناس آزمون onb1', 'workspace_id': org.id, 'occupation_id': occ.id, 'battery_choice': 'short',
                'created_by_id': user('own').id})
pos.state = 'open'
inv = A.create({'workspace_id': org.id, 'instrument_id': emp.id, 'invitee_name': INVITEE})
# 2. a back-office clinical panel: a clinician whose licence number is verified
def bo(name, purpose):
    p = env['res.partner'].search([('name', '=', name), ('is_company', '=', True)], limit=1) or env['res.partner'].create({'name': name, 'is_company': True})
    w = W.search([('partner_id', '=', p.id)], limit=1) or W.create({'name': name, 'purpose': purpose, 'partner_id': p.id,
                                                                     **({'escalation_contact_id': p.id} if purpose == 'clinical' else {})})
    w.state = 'active'
    return w
def mem(w, n, role):
    m = M.with_context(active_test=False).search([('workspace_id', '=', w.id), ('user_id', '=', user(n).id)], limit=1) \
        or M.create({'workspace_id': w.id, 'user_id': user(n).id, 'role': role})
    m.write({'active': True})
    return m
wcl = bo('مرکز onb1 وب', 'clinical')
mem(wcl, 'own', 'owner')
mcl = mem(wcl, 'cl', 'clinician')
mcl.write({'license_number': 'NZ-77'})
mcl.action_verify()
# 3. a panel the EOT team suspends: one finished result of a participant, one open invitation
wsu = bo('پنل onb1 توقف وب', 'education')
osu = mem(wsu, 'own', 'owner')
done = env['ts.attempt'].search([('workspace_id', '=', wsu.id), ('user_id', '=', user('part').id), ('state', '=', 'done')], limit=1)
if not done:
    a = A.sudo().create({'workspace_id': wsu.id, 'instrument_id': edu.id, 'invitee_name': 'شرکت‌کنندهٔ توقف onb1',
                         'invited_by_id': osu.user_id.id})
    done = a.action_accept(user('part'), share=True)
    done.give_consent()
    items = done.active_items()
    for n, label in enumerate(['ریاضی', 'هنر', 'ورزش', 'زبان']):
        f = done.ts_add_field(label)
        for i, it in enumerate(items):
            done.ts_save_cell(f, it.id, (i * (n %% 3 + 1) + 2 * n + i // 5) %% 5 + 1)
        done.ts_finish_field(f)
    assert done.action_submit()
open_inv = A.create({'workspace_id': wsu.id, 'instrument_id': edu.id, 'invitee_name': 'دعوت باز توقف onb1'})
wsu.action_suspend()
slug = env['ts.instrument'].search([('state', '=', 'published'), ('purpose', '!=', 'employment'), ('slug', '!=', False)], limit=1).slug
env.cr.commit()
print('IDS', org.id, pos.id, inv.token, wcl.id, mcl.id, wsu.id, done.id, open_inv.token)
print('SLUG', slug)
""" % (L, PH, INVITEE, FAKE_PORT))
m = re.search(r'IDS (\d+) (\d+) (\S+) (\d+) (\d+) (\d+) (\d+) (\S+)', out)
assert m, out[-2500:]
ORG, POS, TOK_INV, WCL, MCL, WSU, ATT, TOK_OPEN = m.groups()
SLUG = re.search(r'SLUG (\S+)', out).group(1)


def raw(c, path, data=None, headers=None):
    """One request of client `c` with extra headers; returns (status, headers, body)."""
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    h = {'Host': c.host, 'X-Forwarded-Proto': 'https'}
    h.update(headers or {})
    r = urllib.request.Request(lib.BASE + urllib.parse.quote(path, safe="/?=&%:#;,+"), data=body, headers=h)
    try:
        resp = c.op.open(r, timeout=60)
        return resp.status, resp.headers, resp.read().decode('utf-8', 'ignore')
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode('utf-8', 'ignore')


def ajax(c, path, data):
    st, h, body = raw(c, path, data, {'X-TS-Auth': '1'})
    try:
        return st, h, json.loads(body)
    except ValueError:
        return st, h, {}


def session_cookie(h):
    return [v for v in (h.get_all('Set-Cookie') or []) if v.startswith('session_id=')]


def get(c, path):
    st, loc, body = c.req(path)
    for _ in range(3):
        if st in (301, 302, 303) and loc:
            st, loc, body = c.req(path_of(loc))
            continue
        break
    return st, body


def last_code(phone):
    for path, q in reversed(REQS):
        if path == 'sms/send' and q.get('receptor') == phone:
            mm = re.search(r'#(\d{6})\s*$', q.get('message', '')) or re.search(r'(\d{6})', q.get('message', ''))
            if mm:
                return mm.group(1), q['message']
    return None, ''


def age_codes():
    shell("env.cr.execute(\"update ts_signup_otp set create_date = create_date - interval '2 hours'\"); env.cr.commit()")


def fa(s):
    return s.translate(FA)


def start(c, nxt='/my'):
    st, _, page = c.req('/signup' + ('' if nxt == '/my' else '?next=' + nxt))
    return c.csrf(page)


# ================================================================ 1. one sign-in page, eot.ir untouched
pub = Client(TS)
st, _, page = pub.req('/signup')
check('S01 /signup: «ورود یا ثبت‌نام», one h1, the number field (tel, numeric, autocomplete tel, ltr)',
      st == 200 and '<h1>ورود یا ثبت‌نام</h1>' in page and page.count('<h1') == 1
      and re.search(r'<input id="tsa_phone" name="phone" type="tel" dir="ltr" inputmode="numeric" autocomplete="tel"', page) is not None, str(st))
check('S02 the code field is ready for the SMS autofill (one-time-code, numeric) and «این دستگاه شخصی من است» is ticked',
      'autocomplete="one-time-code"' in page and re.search(r'<input type="checkbox" name="personal" value="1"[^>]*checked', page) is not None
      and 'این دستگاه شخصی من است' in page)
check('S03 the e-mail way is a quiet link «با ایمیل ثبت‌نام کرده بودید؟» to /web/login?email=1, terms link to /privacy',
      'با ایمیل ثبت‌نام کرده بودید؟' in page and 'href="/web/login?email=1"' in page and '/privacy' in page)
check('S04 no name field and no password field on the sign-in', 'name="name"' not in page and 'name="password"' not in page)
st, _, page = pub.req('/login')
check('S05 /login is the same page', st == 200 and 'id="tsa_phone"' in page, str(st))
st, _, page = pub.req('/web/login')
check('S06 /web/login on talentsearch.ir shows the mobile sign-in', st == 200 and 'id="tsa_phone"' in page and 'name="password"' not in page, str(st))
st, _, page = pub.req('/web/login?redirect=/my/workspaces/new')
check('S07 /web/login?redirect= keeps the return path (next) and says why',
      'name="next" value="/my/workspaces/new"' in page and 'برای ساخت پنل' in page)
st, _, page = pub.req('/web/login?email=1')
check('S08 /web/login?email=1 is the e-mail sign-in («ورود با ایمیل», password)', st == 200 and 'ورود با ایمیل' in page
      and 'name="password"' in page and 'id="tsa_phone"' not in page, str(st))
st, loc, _ = pub.req('/web/signup')
check('S09 the stock e-mail sign-up leads to the mobile sign-in', st in (302, 303) and path_of(loc).startswith('/signup'), loc)
st, loc, _ = pub.req('/web/signup?redirect=/join/x')
check('S10 ...except for a colleague invitation bound to an e-mail (/join/)', not (st in (302, 303) and path_of(loc).startswith('/signup')), '%s %s' % (st, loc))
st, _, page = pub.req('/')
check('S11 the header «ورود» leads to /signup', st == 200 and re.search(r'<a[^>]*href="/signup"[^>]*>\s*ورود\s*</a>', page) is not None, str(st))
st, body = get(pub, '/assessments/%s' % SLUG)
check('S12 «شروع سنجه» for a visitor goes to the mobile sign-in with next=', st == 200 and '/signup?next=' in body, str(st))
eot = Client(EOT)
st, _, page = eot.req('/web/login')
check('S13 eot.ir /web/login is untouched (password form, no mobile sign-in)', st == 200 and 'name="password"' in page
      and 'tsa_phone' not in page and 'ورود یا ثبت‌نام' not in page, str(st))
check('S14 eot.ir has no /signup and no /login', eot.req('/signup')[0] == 404 and eot.req('/login')[0] == 404)
st, loc, _ = eot.req('/web/signup')
check('S15 eot.ir /web/signup is not sent to the mobile sign-in', '/signup?' not in loc and not path_of(loc or '/x').startswith('/signup'), '%s %s' % (st, loc))

# ================================================================ 2. the two states without reload (JSON), WebOTP line, cookie
c1 = Client(TS)
tok = start(c1, '/invite/' + TOK_INV)
st, h, j = ajax(c1, '/signup/send', {'csrf_token': tok, 'phone': fa(PH['new']), 'next': '/invite/' + TOK_INV,
                                     'personal_shown': '1', 'personal': '1'})
check('J01 a number in Persian digits -> JSON: code state, the number shown formatted, about 60 s to resend',
      st == 200 and j.get('ok') and j.get('state') == 'code' and j.get('phone_fa') == '۰۹۱۲ ۷۷۷ ۸۸۰۱' and 50 <= (j.get('wait') or 0) <= 60, str(j)[:200])
code, body = last_code(PH['new'])
lines = body.split('\n')
check('J02 the SMS: «استعدادیاب / کد ورود: … / این کد را به کسی ندهید.» and the last line «@talentsearch.ir #code», <= 140 characters',
      bool(code) and lines[0] == 'استعدادیاب' and lines[1] == 'کد ورود: %s' % code and lines[2] == 'این کد را به کسی ندهید.'
      and re.match(r'^@([\w-]+\.)*talentsearch\.ir #%s$' % code, lines[-1]) is not None and len(body) <= 140, repr(body))
st, h, j = ajax(c1, '/signup/verify', {'csrf_token': tok, 'code': '۱۲۳', 'next': '/invite/' + TOK_INV})
check('J03 a short code -> «کد ۶ رقمی است.» inline, still on the code state', j.get('state') == 'code' and j.get('msg') == 'کد ۶ رقمی است.', str(j)[:160])
wrong = '000000' if code != '000000' else '111111'
st, h, j = ajax(c1, '/signup/verify', {'csrf_token': tok, 'code': wrong, 'next': '/invite/' + TOK_INV})
check('J04 a wrong code -> «این کد درست نیست. دوباره امتحان کنید.»', not j.get('ok') and j.get('msg') == 'این کد درست نیست. دوباره امتحان کنید.', str(j)[:160])
sid_before = [k.value for k in c1.jar if k.name == 'session_id']
st, h, j = ajax(c1, '/signup/verify', {'csrf_token': tok, 'code': fa(code[:3]) + ' ' + fa(code[3:]), 'next': '/invite/' + TOK_INV})
ck = session_cookie(h)
check('J05 the right code in Persian digits signs in and returns to next (no name step)',
      j.get('ok') and j.get('redirect') == '/invite/' + TOK_INV, str(j)[:160])
check('J06 «this is my personal device» -> the session cookie lasts 30 days (Max-Age=2592000)',
      len(ck) == 1 and 'Max-Age=2592000' in ck[0] and 'HttpOnly' in ck[0], str(ck)[:200])
check('J06b the session id changes at the mobile sign-in (no fixation)',
      bool(sid_before) and len(ck) == 1 and ck[0].split(';')[0] != 'session_id=' + sid_before[0], '%s' % bool(sid_before))
st, _, page = c1.req('/invite/' + TOK_INV)
st, loc, _ = c1.req('/invite/%s/accept' % TOK_INV, {'csrf_token': c1.csrf(page), 'share': '1'})
info = shell("u = env['res.users'].search([('login', '=', '%s')]); a = env['ts.assignment'].search([('token', '=', '%s')]); "
             "print('N', u.partner_id.ts_name_unknown, u.name == %r, a.client_id.name == %r)" % (PH['new'], TOK_INV, INVITEE, INVITEE))
check('J07 accepting an invitation keeps the name the panel wrote on the invitation only: the panel sees it, the account '
      'stays without a name until the person gives one',
      st in (302, 303) and '/take/' in loc and 'N True False True' in info, '%s %s' % (loc, info.strip()[-30:]))
st, body = get(c1, '/my/account')
check('J07b the person\'s own pages never show the formatted mobile as a name', st == 200 and '0912 777 8801' not in body, str(st))

c2 = Client(TS)
tok = start(c2)
ajax(c2, '/signup/send', {'csrf_token': tok, 'phone': PH['new2'], 'next': '/my', 'personal_shown': '1'})
code2, _ = last_code(PH['new2'])
st, h, j = ajax(c2, '/signup/verify', {'csrf_token': tok, 'code': code2, 'next': '/my'})
ck = session_cookie(h)
check('J08 the box unticked -> a browser-session cookie (no Max-Age, no Expires)',
      j.get('ok') and len(ck) == 1 and 'Max-Age' not in ck[0] and 'Expires' not in ck[0], str(ck)[:200])
st, body = get(c2, '/my/workspaces/new?kind=school')
check('J09 a mobile-only account is asked «نام شما» when it makes a panel', st == 200 and 'name="own_name"' in body, str(st))
st, _, page = c2.req('/my/workspaces/new/create', {'csrf_token': c2.csrf(body), 'name': 'مدرسهٔ موبایلی onb1', 'kind': 'school',
                                                   'terms': '1'})
check('J10 without the name the form comes back with a clear message', st == 200 and 'نام و نام خانوادگی خود را بنویسید' in page, str(st))
st, loc, _ = c2.req('/my/workspaces/new/create', {'csrf_token': c2.csrf(page), 'name': 'مدرسهٔ موبایلی onb1', 'kind': 'school',
                                                  'terms': '1', 'own_name': 'مالک موبایلی onb1'})
info = shell("u = env['res.users'].search([('login', '=', '%s')]); w = env['ts.workspace'].search([('name', '=', 'مدرسهٔ موبایلی onb1'), "
             "('member_ids.user_id', '=', u.id)], limit=1, order='id desc'); print('P', u.name, u.partner_id.ts_name_unknown, w.state, w.self_service)" % PH['new2'])
check('J11 with the name: the panel is made active at once (no approval) and the name is stored',
      st in (302, 303) and '?new=1' in loc and 'P مالک موبایلی onb1 False active True' in info, '%s %s' % (loc, info.strip()[-60:]))
st, body = get(c2, path_of(loc))
check('J12 the new panel shows no approval text', st == 200 and 'در انتظار تأیید' not in body and 'پس از تأیید' not in body, str(st))

# ================================================================ 3. e-mail sign-in keeps Odoo's cookie on both sites
for host in (TS, EOT):
    c = Client(host)
    _, _, p = c.req('/web/login?email=1')
    st, h, _ = raw(c, '/web/login', {'csrf_token': c.csrf(p), 'login': L['mail'], 'password': pw[L['mail']], 'redirect': '/my'})
    ck = session_cookie(h)
    check('C01 e-mail sign-in on %s: Odoo\'s own session cookie, not the 30-day one' % host,
          st in (302, 303) and len(ck) == 1 and 'Max-Age=2592000' not in ck[0] and 'Max-Age=' in ck[0], str(ck)[:160])

# ================================================================ 4. staff numbers, lock, help
cs = Client(TS)
tok = start(cs)
ajax(cs, '/signup/send', {'csrf_token': tok, 'phone': PH['staff'], 'next': '/my'})
code_s, _ = last_code(PH['staff'])
st, h, j = ajax(cs, '/signup/verify', {'csrf_token': tok, 'code': code_s, 'next': '/my'})
check('K01 a number of a staff (internal) account is refused with «… از ورود با ایمیل استفاده کنید.»',
      not j.get('ok') and j.get('msg') == 'این شماره به حساب کارکنان وصل است؛ از ورود با ایمیل استفاده کنید.', str(j)[:200])
check('K02 ...and nobody is signed in', cs.req('/my')[0] in (302, 303))

age_codes()
cl_ = Client(TS)
tok = start(cl_)
ajax(cl_, '/signup/send', {'csrf_token': tok, 'phone': PH['lock'], 'next': '/my'})
code_l, _ = last_code(PH['lock'])
bad = '000000' if code_l != '000000' else '111111'
outs = [ajax(cl_, '/signup/verify', {'csrf_token': tok, 'code': bad, 'next': '/my'})[2].get('key') for _ in range(5)]
age_codes()
st, h, j = ajax(cl_, '/signup/send', {'csrf_token': tok, 'resend': '1', 'next': '/my'})
code_l2, _ = last_code(PH['lock'])
outs += [ajax(cl_, '/signup/verify', {'csrf_token': tok, 'code': bad, 'next': '/my'})[2].get('key') for _ in range(5)]
check('K03 ten wrong codes for one number (a new code in between does not reset the count) lock it',
      outs[:5] == ['wrong'] * 5 and outs[-1] == 'locked' and j.get('ok'), str(outs))
st, h, j = ajax(cl_, '/signup/verify', {'csrf_token': tok, 'code': code_l2, 'next': '/my'})
check('K04 while locked even the right code is refused with the 15-minute message',
      j.get('key') == 'locked' and '۱۵ دقیقه' in (j.get('msg') or '') and cl_.req('/my')[0] in (302, 303), str(j)[:160])
age_codes()
st, h, j = ajax(cl_, '/signup/send', {'csrf_token': tok, 'resend': '1', 'next': '/my'})
check('K05 ...and no new code is sent while locked', j.get('key') == 'locked' and last_code(PH['lock'])[0] == code_l2, str(j)[:120])

age_codes()
ch = Client(TS)
tok = start(ch)
st, h, j = ajax(ch, '/signup/send', {'csrf_token': tok, 'phone': PH['help'], 'next': '/my'})
st, h, j1 = ajax(ch, '/signup/send', {'csrf_token': tok, 'resend': '1', 'next': '/my'})
check('K06 asking again within the minute is refused (server cooldown), the countdown comes back', j1.get('key') == 'cooldown' and (j1.get('wait') or 0) > 0, str(j1)[:120])
age_codes()
st, h, j1 = ajax(ch, '/signup/send', {'csrf_token': tok, 'resend': '1', 'next': '/my'})
age_codes()
st, h, j2 = ajax(ch, '/signup/send', {'csrf_token': tok, 'resend': '1', 'next': '/my'})
check('K07 «کد تازه را فرستادیم؛ تا ۵ دقیقه معتبر است.» and the resend count reaches the help threshold (2)',
      j1.get('msg') == 'کد تازه را فرستادیم؛ تا ۵ دقیقه معتبر است.' and j2.get('resends') == 2 and j2.get('help_after') == 2, '%s %s' % (str(j1)[:80], str(j2)[:80]))
st, _, page = ch.req('/signup?step=code')
tag = re.search(r'<details[^>]*id="tsa-help"[^>]*>', page)
check('K08 after two resends the page (without script) opens «کد نرسید؟» help', st == 200 and tag and 'hidden' not in tag.group(0), tag.group(0) if tag else str(st))
# UX T7 P3-1: the code step is marked so the intro and «why» fold away (signin.scss); R9 stays: one field, one-time-code,
# numeric keyboard, Persian digits accepted by the pattern
code_in = re.search(r'<input[^>]*id="tsa_code"[^>]*>', page)
check('K09 the code step: data-tsa-state="code", «کد تأیید ۶ رقمی», one-time-code + numeric + Persian-digit pattern',
      'data-tsa-state="code"' in page and 'کد تأیید ۶ رقمی' in page and code_in and 'autocomplete="one-time-code"' in code_in.group(0)
      and 'inputmode="numeric"' in code_in.group(0) and '۰-۹' in code_in.group(0), code_in.group(0)[:200] if code_in else '')

# ================================================================ 5. e-mail account: offer once, /my/phone
cm = Client(TS)
assert cm.login(L['mail'], pw[L['mail']])
st, body = get(cm, '/my')
check('M01 an e-mail account without a mobile is offered, once, to link one', st == 200 and 'id="ts-home-phone"' in body, str(st))
st, body = get(cm, '/my')
check('M02 ...and not again', st == 200 and 'id="ts-home-phone"' not in body, str(st))
st, _, page = cm.req('/my/phone')
st, loc, _ = cm.req('/my/phone/send', {'csrf_token': cm.csrf(page), 'phone': fa(PH['new'])})
check('M03 a number another account holds: the same answer as a normal send (nothing to enumerate), and no SMS goes there',
      'msg=sent' in loc and 'pending=1' in loc and last_code(PH['new'])[0] == code, loc)
st, _, page = cm.req('/my/phone?pending=1')
st, loc, _ = cm.req('/my/phone/verify', {'csrf_token': cm.csrf(page), 'code': '123456'})
st, body = get(cm, path_of(loc))
check('M03b ...and any code is refused with the neutral text', 'msg=wrong' in loc and 'این کد پذیرفته نشد' in body, loc)
shell("env.cr.execute(\"update ts_phone_otp set create_date = create_date - interval '2 hours' where user_id = "
      "(select id from res_users where login = '%s')\"); env.cr.commit()" % L['mail'])
st, _, page = cm.req('/my/phone')
st, loc, _ = cm.req('/my/phone/send', {'csrf_token': cm.csrf(page), 'phone': fa(PH['mail'])})
code_m, body_m = last_code(PH['mail'])
check('M04 the linking code is sent (its SMS ends with the WebOTP line too)', 'msg=sent' in loc and bool(code_m)
      and body_m.split('\n')[-1].endswith(' #' + str(code_m)), '%s %r' % (loc, body_m))
st, _, page = cm.req('/my/phone?pending=1')
st, loc, _ = cm.req('/my/phone/verify', {'csrf_token': cm.csrf(page), 'code': fa(code_m[:3]) + ' ' + fa(code_m[3:])})
info = shell("print('T', env['res.users'].search([('login', '=', '%s')]).partner_id.ts_phone)" % L['mail'])
check('M05 /my/phone takes the code in Persian digits with a space; the mobile is linked', 'msg=verified' in loc and 'T %s' % PH['mail'] in info, loc)

# ================================================================ 6. panel side: HR position limit, suspend, licence badge
own = Client(TS)
assert own.login(L['own'], pw[L['own']])
B = '/my/workspaces/%s/positions/%s' % (ORG, POS)
st, body = get(own, B)
check('H01 a brand-new organization panel: the position page offers the invitation form at once, with the first-week line',
      st == 200 and 'name="people"' in body and 'در هفتهٔ اول روزانه تا' in body, str(st))
q = shell("w = env['ts.workspace'].browse(%s); l, left = w.ts_invite_quota(); "
          "env['ir.config_parameter'].sudo().set_str('ts_panel.new_panel_daily_invites', str(l - left + 1)); env.cr.commit(); print('Q', l, left)" % ORG)
people = 'داوطلب یک onb1، one.onb1@example.invalid\nداوطلب دو onb1، two.onb1@example.invalid'
st, loc, _ = own.req(B + '/invite', {'csrf_token': own.csrf(body), 'people': people, 'extra_time': '1.0'})
st, body = get(own, B)
check('H02 two people when one is left today: refused whole, in Persian digits, and the typed lines come back',
      'امروز فقط ۱ دعوت دیگر' in body and 'داوطلب دو onb1' in body and 'two.onb1@example.invalid' in body, q.strip()[-20:])
st, loc, _ = own.req(B + '/invite', {'csrf_token': own.csrf(body), 'people': 'داوطلب یک onb1، one.onb1@example.invalid', 'extra_time': '1.0'})
n = shell("print('C', env['ts.assignment'].search_count([('position_id', '=', %s)])); "
          "env['ir.config_parameter'].sudo().set_str('ts_panel.new_panel_daily_invites', '50'); env.cr.commit()" % POS)
check('H03 one person fits: the HR position invitation is made (no e-mail leaves a clone)', 'C 1' in n, n.strip()[-10:])

st, body = get(own, '/my/workspaces/%s' % WSU)
check('U01 a suspended panel shows «این پنل موقتاً متوقف شده است…» to its members', st == 200 and 'این پنل موقتاً متوقف شده است' in body, str(st))
st, body = get(Client(TS), '/invite/%s' % TOK_OPEN)
check('U02 an open invitation of a suspended panel explains the pause and offers no accept',
      st == 200 and 'این دعوت فعلاً در دسترس نیست' in body and '/accept' not in body, str(st))
part = Client(TS)
assert part.login(L['part'], pw[L['part']])
st, body = get(part, '/my/assessments/%s' % ATT)
check('U03 the participant still sees his own result', st == 200 and 'نتیجه' in body, str(st))

MP = '/my/workspaces/%s/members/%s' % (WCL, MCL)
st, body = get(own, MP)
check('L01 the member page shows the badge «پروانهٔ تأییدشده»', st == 200 and 'ts-pill--ok">پروانهٔ تأییدشده' in body, str(st))
shell("env['ts.workspace.member'].browse(%s).write({'license_number': 'NZ-78'}); env.cr.commit()" % MCL)
st, body = get(own, MP)
check('L02 a changed number drops the badge (registered, not yet checked) without touching the work',
      st == 200 and 'ts-pill--ok">پروانهٔ تأییدشده' not in body and 'ثبت‌شده، هنوز بررسی نشده' in body, str(st))
shell("m = env['ts.workspace.member'].browse(%s); m.write({'license_number': 'NZ-77'}); m.action_verify(); env.cr.commit()" % MCL)

# ================================================================ 7. return paths, e-mail sign-up, sign-out (risk review)
rp = Client(TS)
EVIL = ['/\t/evil.example', '/%09/evil.example', '//evil.example', '/\\evil.example', '/%2F/evil.example', '/%5C/evil.example',
        '/\n/evil.example', 'https://evil.example']
pages = [rp.req('/signup?next=' + urllib.parse.quote(e, safe=''))[2] for e in EVIL] + \
        [rp.req('/web/login?redirect=' + urllib.parse.quote(e, safe=''))[2] for e in EVIL]
check('R01 a return path that could lead to another site (tab, newline, encoded, backslash, //) becomes /my',
      all('name="next" value="/my"' in p and 'evil.example' not in p for p in pages), sum(1 for p in pages if 'evil.example' in p))
sp = Client(TS)
_, _, p = sp.req('/signup')
st, loc, _ = sp.req('/web/signup', {'csrf_token': sp.csrf(p), 'login': 'onb1.signup@example.invalid', 'name': 'ثبت‌نام ایمیلی',
                                    'password': 'Onb1-pass-91!', 'confirm_password': 'Onb1-pass-91!'})
n = shell("print('S', env['res.users'].with_context(active_test=False).search_count([('login', '=', 'onb1.signup@example.invalid')]))")
check('R02 POST /web/signup on talentsearch.ir makes no e-mail account (only tokens and /join/ invitations may)',
      st in (302, 303) and path_of(loc).startswith('/signup') and 'S 0' in n, '%s %s %s' % (st, loc, n.strip()[-5:]))
_, _, p = c1.req('/my/account')
st, h, _ = raw(c1, '/web/session/logout', {'csrf_token': c1.csrf(p), 'redirect': '/'})        # POST in Odoo 20
ck = session_cookie(h)
check('R03 sign-out (a POST form in the header, as Odoo 20 needs) ends the 30-day choice: the next cookie is Odoo\'s own',
      'class="ts-appnav__out"' in p and st in (302, 303) and c1.req('/my')[0] in (302, 303)
      and all('Max-Age=2592000' not in c for c in ck), '%s %s' % (st, str(ck)[:160]))
_, _, p = c1.req('/web/login?email=1')
st, h, _ = raw(c1, '/web/login', {'csrf_token': c1.csrf(p), 'login': L['mail'], 'password': pw[L['mail']], 'redirect': '/my'})
ck = session_cookie(h)
check('R04 a password sign-in in the same browser never inherits the 30-day cookie',
      st in (302, 303) and len(ck) == 1 and 'Max-Age=2592000' not in ck[0], str(ck)[:160])

# ================================================================ 8. SMS switched off: the e-mail sign-in is the way in
shell("env.company.sudo().ts_sms_otp = False; env.cr.commit()")
st, _, page = Client(TS).req('/web/login')
check('X01 with mobile sign-in off, /web/login on talentsearch.ir is the e-mail sign-in (never a page without a form); '
      'e-mail sign-up stays closed',
      st == 200 and 'name="password"' in page and 'id="tsa_phone"' not in page and Client(TS).req('/web/signup')[0] in (302, 303), str(st))
shell("env.company.sudo().ts_sms_otp = True; env.cr.commit()")
srv.shutdown()
summary()
