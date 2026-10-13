#!/usr/bin/env python3
"""onb2 over HTTP against a served CLONE with a LOCAL fake Kavenegar (no SMS or e-mail leaves the machine):
one-tap invitations (welcome screen, GET never consumes, the POST is the consent, scoped sign-in only with the delivery
secret of the system's own SMS / e-mail and only into an account made now or a phone-only one, a copied link always gets a
code, scope enforcement on every route family and on other websites, device binding with «این دستگاه شخصی من است»,
mismatch, minors on one screen, fairness questions at the end, 12-character short links, rate limits, no-referrer) and
test first for individuals (start screen, guest attempt keyed by an HttpOnly cookie never in an address, result gate,
claim only from the gate, 48-hour clean-up, funnel without robots). eot.ir must stay exactly as it was.
    ts_http_onb2.py DB PORT"""
import http.cookiejar, http.server, importlib.util, json, os, re, sys, threading, urllib.error, urllib.parse, urllib.request

FAKE_PORT = 18097 + 10 * int(os.environ.get('TS_SLOT', '0'))   # one fake Kavenegar per rehearsal slot (onb1 uses 18094)
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, summary, shell, ensure_user, path_of = lib.Client, lib.check, lib.summary, lib.shell, lib.ensure_user, lib.path_of
TS, EOT = 'talentsearch.ir', 'www.eot.ir'
REQS, MID = [], [910000]


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


class AnyScheme(http.cookiejar.DefaultCookiePolicy):
    """The clone is reached over plain http behind a forwarded https header: send the Secure cookies back anyway."""
    def return_ok_secure(self, cookie, request):
        return True


def client(host=TS):
    c = Client(host)
    c.jar.set_policy(AnyScheme())
    return c


FA = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')
PH = {'sms': '09126654391', 'manual': '09126654392', 'mis': '09126654393', 'other': '09126654394', 'guest': '09126654395',
      'guest2': '09126654396', 'gate': '09126654397', 'dev': '09126654398', 'emq': '09126654399', 'emr': '09126654380',
      'hr': '09126654379'}
EMAIL = 'ts.onb2.cand.http@example.invalid'
EMAIL2 = 'ts.onb2.cand2.http@example.invalid'
L = {n: 'ts.onb2.%s.http@example.invalid' % n for n in ('other', 'minor')}
pw = {u: ensure_user(u) for u in L.values()}

out = shell(r"""
L, PH, EMAIL, EMAIL2 = %r, %r, %r, %r
import re as _re
from unittest.mock import patch
from odoo import fields
from odoo.addons.ts_hire.models.mail import TsAssignmentMail
assert env.cr.dbname.startswith('eot_ts')
env['ir.config_parameter'].sudo().set_str('ts_kavenegar.api_base', 'http://127.0.0.1:%d/v1/%%s/%%s.json')
c = env.company.sudo()
c.write({'kv_lines': '10004346'})
c.write({'kv_enabled': True, 'kv_api_key': 'FAKEKEY', 'kv_sender': '10004346', 'ts_sms_otp': True, 'ts_sms_otp_template_id': False,
         'ts_sms_invite': True, 'ts_sms_result': False})
ICP = env['ir.config_parameter'].sudo()
ICP.set_str('ts_onboard.short_per_minute', '30'); ICP.set_str('ts_onboard.guest_per_hour', '3')
ICP.set_str('ts_onboard.invite_per_minute', '60'); ICP.set_str('ts_onboard.campaign_per_minute', '120')
ICP.set_str('ts_onboard.answers_per_minute', '200')
ICP.set_str('ts_panel.invites_per_hour', '200')
env['ts.rate.hit'].sudo().search([]).unlink()
U = env['res.users'].with_context(active_test=False)
for ph in PH.values():
    for u in U.search([('login', '=', ph)]):
        u.partner_id.sudo().write({'ts_phone': False, 'ts_phone_verified_at': False})
        u.sudo().write({'active': False, 'login': 'old.onb2.%%d' %% u.id})
env['res.partner'].with_context(active_test=False).search([('ts_phone', 'in', list(PH.values()))]).write({'ts_phone': False})
for u in U.search(['|', ('login', 'in', [EMAIL, EMAIL2]), ('email', 'in', [EMAIL, EMAIL2])]):
    u.sudo().write({'active': False, 'login': 'old.onb2.%%d' %% u.id, 'email': False})
env['ts.signup.otp'].sudo().search([('phone', 'in', list(PH.values()))]).unlink()
env['ts.signup.lock'].sudo().search([('phone', 'in', list(PH.values()))]).unlink()
env.cr.execute("update ts_signup_otp set create_date = create_date - interval '2 hours'")
other = env['res.users'].search([('login', '=', L['other'])])
other.partner_id.write({'ts_phone': PH['other'], 'ts_phone_verified_at': fields.Datetime.now()})
W, A = env['ts.workspace'], env['ts.assignment'].sudo()
def bo(name, purpose):
    p = env['res.partner'].search([('name', '=', name), ('is_company', '=', True)], limit=1) or env['res.partner'].create({'name': name, 'is_company': True})
    w = W.search([('partner_id', '=', p.id)], limit=1) or W.create({'name': name, 'purpose': purpose, 'partner_id': p.id,
                                                                     **({'escalation_contact_id': p.id} if purpose == 'clinical' else {})})
    w.state = 'active'
    return w
wcl = bo('مرکز onb2 وب', 'clinical')
adult = env['ts.instrument'].search([('state', '=', 'published'), ('audience', '=', 'adult'), ('purpose', '!=', 'employment'),
                                     ('code', 'not in', ('TALENT-INV-15', 'inventory_002'))], order='id', limit=1)
def inv(name, **kw):
    return A.create(dict({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': name}, **kw))
# the system's own SMS (through the local fake Kavenegar): its link carries the delivery secret
t_sms = inv('مریم آزمایشی', invitee_phone=PH['sms'], sms_consent=True)
t_sms2 = inv('مریم آزمایشی دوم')
t_sms2._ts_mark_delivered('sms', phone=PH['sms'])
t_dev = inv('دستگاه مشترک', invitee_phone=PH['dev'], sms_consent=True)
# the system's own e-mail: rendered from the real template, never sent (the transport is replaced)
t_email = inv('داوطلب ایمیلی', invitee_email=EMAIL)
t_email2 = inv('داوطلب ایمیلی دوم', invitee_email=EMAIL2)
MAILS = {}
def fake_tpl(self, xmlid, email_to=None):
    MAILS[self.id] = env.ref(xmlid).sudo()._render_field('body_html', [self.id])[self.id]
    return True, ''
with patch.object(TsAssignmentMail, '_ts_send_template', fake_tpl):
    t_email._ts_send_invite_email()
    t_email2._ts_send_invite_email()
def dl(t):
    m_ = _re.search(r'[?&](?:amp;)?d=([A-Za-z0-9_-]{22,})', str(MAILS.get(t.id) or ''))
    return m_.group(1) if m_ else '-'
t_manual = inv('شمارهٔ دستی', invitee_phone=PH['manual'])
t_link = inv('پیوند ساده')
t_mis = inv('ناهمخوان')
t_mis._ts_mark_delivered('sms', phone=PH['mis'])
t_dec = inv('نمی‌خواهد')
minor = env['ts.panel.client'].sudo().create({'workspace_id': wcl.id, 'name': 'نوجوان آزمایشی onb2', 'age_group': 'minor'})
t_minor = inv('نوجوان آزمایشی onb2', client_id=minor.id)
t_child = ''
bc = env['ts.battery'].sudo().search([('code', '=', 'BAT-CHILD-1'), ('state', '=', 'published')], limit=1)
if bc:
    try:
        with env.cr.savepoint():
            ch = env['ts.panel.client'].sudo().create({'workspace_id': wcl.id, 'name': 'کودک آزمایشی onb2', 'age_group': 'minor'})
            t_child = A.create({'workspace_id': wcl.id, 'battery_id': bc.id, 'instrument_id': bc.ts_first_instrument().id,
                                'invitee_name': 'ولی کودک آزمایشی', 'client_id': ch.id}).token
    except Exception as e:
        print('NOCHILD', type(e).__name__, str(e)[:100])
# an employment panel with an open position; a candidate whose battery is finished (for the fairness questions)
org = bo('شرکت onb2 وب', 'employment')
occ = env['ts.onet.occupation'].search([], limit=1)
P = env['ts.hire.position'].sudo()
P.search([('workspace_id', '=', org.id)]).write({'state': 'closed'})
hrm = env['ts.workspace.member'].sudo().with_context(active_test=False).search([('workspace_id', '=', org.id), ('role', '=', 'hr_admin')], limit=1) \
    or env['ts.workspace.member'].sudo().create({'workspace_id': org.id, 'user_id': env['res.users'].search([('login', '=', L['minor'])]).id, 'role': 'hr_admin'})
pos = P.create({'name': 'کارشناس آزمون onb2', 'workspace_id': org.id, 'occupation_id': occ.id, 'battery_choice': 'short',
                'created_by_id': hrm.user_id.id})
pos.state = 'open'
def pinv(name):
    return A.with_user(hrm.user_id).sudo().create({'workspace_id': org.id, 'battery_id': pos.battery_id.id, 'position_id': pos.id,
        'instrument_id': pos.battery_id.ts_first_instrument().id, 'invitee_name': name, 'invited_by_id': hrm.user_id.id,
        'note': 'ارزیابی برای موقعیت «%%s»' %% pos.name})
t_emp = pinv('داوطلب onb2')
t_emp._ts_mark_delivered('sms', phone=PH['guest2'])
# a candidate invited by SMS (its link carries the secret): the scoped session drives the timed tasks of the battery
t_hr = A.with_user(hrm.user_id).sudo().create({'workspace_id': org.id, 'battery_id': pos.battery_id.id, 'position_id': pos.id,
    'instrument_id': pos.battery_id.ts_first_instrument().id, 'invitee_name': 'داوطلب زمان‌دار onb2',
    'invited_by_id': hrm.user_id.id, 'invitee_phone': PH['hr'], 'sms_consent': True})
t_fair = pinv('داوطلب پایان onb2')
cand = env['res.users'].search([('login', '=', L['other'])])
t_fair.action_accept(cand, share=True)
for t in t_fair.ts_battery_attempts():
    t.sudo().write({'state': 'done', 'submitted_at': fields.Datetime.now(), 'released': True})
t_fair.invalidate_recordset()
env.cr.commit()
print('TOK', t_sms.token, t_sms2.token, t_email.token, t_manual.token, t_link.token, t_mis.token, t_dec.token, t_minor.token,
      t_child or '-', t_emp.token, t_fair.id, t_sms.short_code, t_fair.state)
print('TOK2', t_email2.token, t_dev.token, t_dev.short_code, dl(t_email), dl(t_email2), t_sms.delivered_via, t_dev.delivered_via)
print('TOK3', t_hr.token, '|'.join(t.access_token for t in t_fair.ts_battery_attempts()))
st = env['ts.instrument'].sudo().ts_starter()
print('STARTER', st.slug, st.code, st.active_item_count, st.duration_minutes)
""" % (L, PH, EMAIL, EMAIL2, FAKE_PORT))
m = re.search(r'TOK (\S+) (\S+) (\S+) (\S+) (\S+) (\S+) (\S+) (\S+) (\S+) (\S+) (\d+) (\S+) (\S+)', out)
assert m, out[-2500:]
T_SMS, T_SMS2, T_EMAIL, T_MANUAL, T_LINK, T_MIS, T_DEC, T_MINOR, T_CHILD, T_EMP, FAIR_ID, SHORT, FAIR_STATE = m.groups()
m2 = re.search(r'TOK2 (\S+) (\S+) (\S+) (\S+) (\S+) (\S+) (\S+)', out)
assert m2, out[-2500:]
T_EMAIL2, T_DEV, SHORT_DEV, DLV_E1, DLV_E2, VIA_SMS, VIA_DEV = m2.groups()
sm = re.search(r'STARTER (\S+) (\S+) (\d+) (\d+)', out)
SLUG, SCODE, SITEMS, SMIN = sm.groups() if sm else ('x', 'x', '0', '0')


def sms_link(phone):
    """The /i/<code>/<secret> of the latest invitation SMS the fake Kavenegar received for `phone`."""
    for path, qd in reversed(REQS):
        if path == 'sms/send' and qd.get('receptor') == phone:
            mm = re.search(r'/i/([a-z0-9]{8,12})/([A-Za-z0-9_-]{22,})', qd.get('message', ''))
            if mm:
                return mm.group(1), mm.group(2)
    return '-', '-'


SHORT_S, DLV_S = sms_link(PH['sms'])
SHORT_D, DLV_D = sms_link(PH['dev'])
SHORT_H, DLV_H = sms_link(PH['hr'])
m3 = re.search(r'TOK3 (\S+) (\S+)', out)
T_HR, FAIR_TOKS = m3.groups() if m3 else ('x', 'x|x')
FAIR_TASK = FAIR_TOKS.split('|')[-1]


def raw(c, path, data=None, headers=None):
    """One request with extra headers -> (status, headers, body)."""
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    h = {'Host': c.host, 'X-Forwarded-Proto': 'https'}
    h.update(headers or {})
    r = urllib.request.Request(lib.BASE + urllib.parse.quote(path, safe="/?=&%:#;,+"), data=body, headers=h)
    try:
        resp = c.op.open(r, timeout=60)
        return resp.status, resp.headers, resp.read().decode('utf-8', 'ignore')
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode('utf-8', 'ignore')


def jpost(c, path, obj):
    """A JSON POST (JSON-RPC and /json routes) -> (status, body)."""
    h = {'Host': c.host, 'X-Forwarded-Proto': 'https', 'Content-Type': 'application/json'}
    r = urllib.request.Request(lib.BASE + path, data=json.dumps(obj).encode(), headers=h)
    try:
        resp = c.op.open(r, timeout=60)
        return resp.status, resp.read().decode('utf-8', 'ignore')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'ignore')


def ajax(c, path, data):
    st, h, body = raw(c, path, data, {'X-TS-Auth': '1'})
    try:
        return st, h, json.loads(body)
    except ValueError:
        return st, h, {}


LOCS = []          # every Location header seen in this suite (the guest token must never appear in one)


def get(c, path, hops=4):
    st, loc, body = c.req(path)
    for _ in range(hops):
        if st in (301, 302, 303) and loc:
            LOCS.append(loc)
            st, loc, body = c.req(path_of(loc))
            continue
        break
    return st, body


def last_code(phone):
    for path, q in reversed(REQS):
        if path == 'sms/send' and q.get('receptor') == phone and '/i/' not in q.get('message', ''):
            mm = re.search(r'#(\d{6})\s*$', q.get('message', '')) or re.search(r'(\d{6})', q.get('message', ''))
            if mm:
                return mm.group(1)
    return None


def sms_count(phone):
    return sum(1 for p, q in REQS if p == 'sms/send' and q.get('receptor') == phone)


def q(code):
    return shell(code)


def masked(phone):
    """The mask of a known number: its last four digits only («*** ۴۳۹۱»; asterisks: bullets read as Persian zeros)."""
    return '*** ' + phone[-4:].translate(FA)


def in_full(phone, page):
    """The number appears whole (Latin or Persian digits, grouped or not), or its first four digits do."""
    s = '%s %s %s' % (phone[:4], phone[4:7], phone[7:])
    return any(x in page for x in (s, s.translate(FA), phone, phone.translate(FA), phone[:4].translate(FA) + '***'))


def cookies(h):
    return h.get_all('Set-Cookie') or []


def logout(c):
    st, page = get(c, '/my')
    c.req('/web/session/logout', {'csrf_token': c.csrf(page)})


# ================================================================ 1. the welcome screen; GET never consumes; the message's secret
pub = client()
st, h, page = raw(pub, '/invite/%s' % T_SMS)
check('W01 the welcome screen: «سلام مریم», who invites, minutes, three lines of what the centre sees and «بیشتر»',
      st == 200 and 'سلام مریم' in page and 'مرکز onb2 وب' in page and 'دقیقه' in page and 'tso-lines' in page
      and '<summary>بیشتر</summary>' in page, str(st))
check('W02 one primary action «موافقم و شروع می‌کنم» and a quiet «نمی‌خواهم شرکت کنم»; no sign-in step, no number field',
      page.count('ts-btn--primary') == 1 and 'موافقم و شروع می‌کنم' in page and 'نمی‌خواهم شرکت کنم' in page
      and 'name="phone"' not in page and 'tsa_phone' not in page)
check('W03 the invitation page sends Referrer-Policy: no-referrer and Cache-Control: no-store',
      h.get('Referrer-Policy') == 'no-referrer' and 'no-store' in (h.get('Cache-Control') or ''), '%s %s' % (h.get('Referrer-Policy'), h.get('Cache-Control')))
raw(pub, '/invite/%s' % T_SMS)
info = q("a = env['ts.assignment'].sudo().search([('token', '=', '%s')]); print('G', bool(a.user_id), bool(a.attempt_id), bool(a.device_hash), a.state)" % T_SMS)
check('W04 opening the link twice (a messenger preview) accepts, binds and signs in nothing; the panel sees «بازشده»',
      'G False False False opened' in info, info.strip()[-60:])
st, loc, _ = pub.req('/my')
check('W05 ...and the visitor is still not signed in', st in (302, 303) and ('/signup' in loc or '/web/login' in loc), loc)
st, h, page = raw(pub, '/i/%s' % SHORT)
check('W06 the plain short link redirects to the invitation with no-referrer', st == 302 and h.get('Location', '').endswith('/invite/' + T_SMS)
      and h.get('Referrer-Policy') == 'no-referrer', '%s %s' % (st, h.get('Location')))
check('W07 new short codes have 12 characters', re.fullmatch(r'[a-z0-9]{12}', SHORT) is not None, SHORT)
nb = client()
gone = [raw(nb, p) for p in ('/invite/%s' % ('x' * 43), '/i/zzzzzzzzzzzz', '/j/zzzzzzzzzzzz', '/c/no-such-open-link',
                             '/i/zzzzzzzzzzzz/%s' % ('y' * 22))]
check('W08 an unknown invitation, short code (with or without a secret) or open link: the one explained link 404',
      all(st == 404 and 'این پیوند باز نمی‌شود' in pg and 'id="ts-link-404"' in pg for st, _h, pg in gone), [x[0] for x in gone])
check('W09 ...the same words for each (nothing tells whether such a link existed), with no-store',
      len({re.sub(r'\s+', ' ', re.search(r'<h1>(.*?)</h1>', pg, re.S).group(1)) for _s, _h, pg in gone if '<h1>' in pg}) == 1
      and all('no-store' in (hh.get('Cache-Control') or '') for _s, hh, _p in gone))
st, h, page = raw(nb, '/start')
check('W10 the guest pages carry no-referrer and no-store too', h.get('Referrer-Policy') == 'no-referrer'
      and 'no-store' in (h.get('Cache-Control') or ''), '%s %s' % (st, h.get('Cache-Control')))
check('W11 the invitation SMS the system sent carries /i/<code>/<secret> (22+ url-safe characters); the e-mails ?d=<secret>',
      SHORT_S == SHORT and re.fullmatch(r'[A-Za-z0-9_-]{22,}', DLV_S) and VIA_SMS == 'sms' and DLV_E1 != '-' and DLV_E2 != '-'
      and len({DLV_S, DLV_E1, DLV_E2}) == 3, '%s %s %s' % (SHORT_S, len(DLV_S), VIA_SMS))
info = q("import json\nsecrets = %r\nK = env['kavenegar.message'].sudo().search([('receptor', 'like', '%s')])\n"
         "n = 0\nfor tbl in ('ts_audit_event', 'kavenegar_message', 'mail_message', 'mail_mail', 'sms_sms', 'ts_assignment', 'ts_funnel_event'):\n"
         "    env.cr.execute('SELECT count(*) FROM %%s t WHERE ' %% tbl + ' OR '.join(['t::text LIKE %%s'] * len(secrets)), ['%%' + s + '%%' for s in secrets])\n"
         "    n += env.cr.fetchone()[0]\n"
         "print('KV', len(K), all(b == '***' for b in K.mapped('body')), n)" % ([DLV_S, DLV_E1, DLV_E2], PH['sms'][1:]))
check('W12 the secret is nowhere on the server: the Kavenegar log keeps «***», no audit row, message, SMS, e-mail, '
      'invitation or funnel row holds it', re.search(r'KV [1-9]\d* True 0', info), info.strip()[-40:])
st, h, _ = raw(nb, '/i/%s/%s' % (SHORT_S, DLV_S))
WLOC = h.get('Location', '')
check('W13 the SMS link /i/<code>/<secret> goes to the welcome screen with ?d=<secret>, no-referrer and no-store',
      st == 302 and WLOC.endswith('/invite/%s?d=%s' % (T_SMS, DLV_S)) and h.get('Referrer-Policy') == 'no-referrer'
      and 'no-store' in (h.get('Cache-Control') or ''), '%s %s' % (st, WLOC[-60:]))
st, page = get(nb, path_of(WLOC))
check('W14 the welcome screen carries the secret as a hidden field of its one form, and «این دستگاه شخصی من است» ticked',
      st == 200 and ('name="d" value="%s"' % DLV_S) in page and page.count(DLV_S) == 1
      and re.search(r'name="personal" value="1" checked="checked"', page) and 'این دستگاه شخصی من است' in page, str(st))

# ================================================================ 2. a copied link gets a code; the message's secret signs in
cp = client()
st, _, page = cp.req('/invite/%s' % T_SMS)
n0 = sms_count(PH['sms'])
st, h, _ = raw(cp, '/invite/%s/accept' % T_SMS, {'csrf_token': cp.csrf(page), 'welcome': '1', 'share': '1', 'personal': '1'})
loc = h.get('Location', '')
info = q("a = env['ts.assignment'].sudo().search([('token', '=', '%s')]); print('CP', bool(a.user_id), bool(a.device_hash))" % T_SMS)
check('A00 the link the panel copied (no secret) of an SMS invitation: a code to the invited number, never a session',
      st == 303 and path_of(loc).startswith('/signup?step=code') and sms_count(PH['sms']) == n0 + 1 and 'CP False False' in info
      and not [c for c in cookies(h) if c.startswith('ts_dev=')], '%s %s' % (loc, info.strip()[-20:]))
cw = client()
st, _, page = cw.req('/invite/%s' % T_SMS)
st, loc, _ = cw.req('/invite/%s/accept' % T_SMS, {'csrf_token': cw.csrf(page), 'welcome': '1', 'share': '1', 'd': 'A' * 22})
info = q("a = env['ts.assignment'].sudo().search([('token', '=', '%s')]); print('CW', bool(a.user_id))" % T_SMS)
check('A00b a wrong secret proves nothing either: a code, no session', st == 303 and path_of(loc).startswith('/signup?step=code')
      and 'CW False' in info, loc)
shell("env.cr.execute(\"update ts_signup_otp set create_date = create_date - interval '2 hours'\"); env.cr.commit()")
st, h, _ = raw(pub, '/i/%s/%s' % (SHORT_S, DLV_S))
st, page = get(pub, path_of(h.get('Location', '')))
n_sms = sms_count(PH['sms'])
st, h, _ = raw(pub, '/invite/%s/accept' % T_SMS, {'csrf_token': pub.csrf(page), 'welcome': '1', 'share': '1', 'personal': '1',
                                                    'd': DLV_S})
loc = h.get('Location', '')
LOCS.append(loc)
dev = [c for c in cookies(h) if c.startswith('ts_dev=')]
check('A01 with the SMS secret, one tap (no number typed, no code): straight to the first question', st == 303 and '/take/' in loc,
      '%s %s' % (st, loc))
check('A02 no second SMS was needed', sms_count(PH['sms']) == n_sms)
check('A03 «این دستگاه شخصی من است» ticked: the invitation is bound to this browser for 30 days (a signed HttpOnly SameSite=Lax cookie)',
      len(dev) == 1 and 'HttpOnly' in dev[0] and 'SameSite=Lax' in dev[0] and 'Max-Age=2592000' in dev[0]
      and re.match(r'ts_dev=[\w-]+\.[0-9a-f]{32};', dev[0]), str(dev)[:160])
info = q("a = env['ts.assignment'].sudo().search([('token', '=', '%s')]); u = a.user_id; t = a.attempt_id; "
         "print('A', u.login, u.partner_id.ts_name_unknown, u.name == a.invitee_name, t.state, bool(t.consent_version), a.welcome_version == t.consent_version, "
         "len(a.device_hash or ''), a.share_level, a.ts_account_made)" % T_SMS)
check('A04 the account of the number is made without the panel\'s name (made by the flow); the POST is the consent '
      '(version recorded); the attempt starts without a consent page; only a digest of the browser token is stored',
      ('A %s True False in_progress True True 64 clinical True' % PH['sms']) in info, info.strip()[-120:])
TAKE1 = path_of(loc)
st, h, page = raw(pub, TAKE1)
check('A05 the player opens directly (no second consent screen), with no-referrer', st == 200 and 'ts-qform' in page
      and 'consent_service' not in page and h.get('Referrer-Policy') == 'no-referrer', str(st))
t_items = re.findall(r'name="q_(\d+)"', page)
st, h, j = ajax(pub, TAKE1 + '/answer', {'csrf_token': pub.csrf(page), 'item': t_items[0] if t_items else '0', 'value': '3'})
check('A06 the scoped session saves answers through the player (its own endpoint)', st == 200 and j.get('ok'),
      '%s %s' % (st, str(j)[:80]))

# ================================================================ 3. the scope: only this invitation, only on talentsearch.ir
info = q("a = env['ts.assignment'].sudo().search([('token', '=', '%s')]); print('ATT', a.attempt_id.id, a.user_id.partner_id.id)" % T_SMS)
ATT1, PID1 = re.search(r'ATT (\d+) (\d+)', info).groups()
for i, path in enumerate(['/my', '/my/assessments', '/my/account', '/my/workspaces', '/my/workspaces/1', '/invite/' + T_LINK,
                          '/i/zzzzzzzzzzzz', '/web', '/odoo', '/assessments?all=1', '/start', '/my/assessments/%s/share' % ATT1]):
    st, loc, _ = pub.req(path)
    check('Q%02d a session scoped to one invitation is sent to the sign-in from %s' % (i + 1, path),
          st == 303 and path_of(loc).startswith('/signup?next='), '%s %s' % (st, loc))
st, _, _ = pub.req('/my/assessments/%s' % ATT1)
check('Q13 ...while its own result page stays reachable (the attempt is not finished: back to the player)', st in (200, 302, 303))
TOK1 = TAKE1.split('/take/')[1].split('/')[0]
st, loc, _ = pub.req('/take/%s' % TOK1)
check('Q14 ...and its player', st == 200, str(st))
RPC = {'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': {}}
jr = [jpost(pub, '/web/dataset/call_kw', dict(RPC, params={'model': 'res.partner', 'method': 'search_read', 'args': [[]],
                                                           'kwargs': {'limit': 1, 'fields': ['name']}})),
      jpost(pub, '/web/session/get_session_info', RPC), jpost(pub, '/mail/data', dict(RPC, params={'fetch_params': ['init_messaging']}))]
check('Q20 JSON-RPC from a scoped session (/web/dataset/call_kw, /web/session/get_session_info, /mail/data): 403, no data',
      all(s == 403 for s, _b in jr) and not any('"result"' in b for _s, b in jr), [s for s, _b in jr])
st, body = jpost(pub, '/json/2/res.partner/search_read', {'domain': [], 'limit': 1})
check('Q21 /json/2 from a scoped session: refused (403, or 401 before it), no data', st in (401, 403)
      and not body.lstrip().startswith('['), '%s %s' % (st, body[:60]))
st, loc, _ = pub.req('/web/image/res.partner/%s/avatar_128' % PID1)
st2, h2, _b2 = raw(pub, '/websocket', headers={'Connection': 'Upgrade', 'Upgrade': 'websocket', 'Sec-WebSocket-Version': '13',
                                                'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ==',
                                                'Origin': 'https://talentsearch.ir'})
# the clone's threaded server refuses every upgrade itself (400; websockets live on the gevent port, which dispatches through
# the same ir.http and its scope guard, tests_onb2 Q02): never a 101 here
check('Q22 /web/image and /websocket are not open to a scoped session (sign-in instead; never a websocket upgrade)',
      st == 303 and path_of(loc).startswith('/signup?next=') and st2 in (303, 400, 403), '%s %s' % (st, st2))
st, loc, _ = pub.req('/zz-onb2-no-such-page')
check('Q23 a website page or attachment (no route, served by the fallback) follows the same rule', st == 303
      and path_of(loc).startswith('/signup?next='), '%s %s' % (st, loc))
st, _, _ = pub.req('/take/%s' % TOK1)
check('Q24 ...and on talentsearch.ir the session itself goes on (its own pages still open)', st == 200, str(st))
st, h, page = raw(pub, '/signup?next=/my')
check('Q15 the sign-in shows the invited number by its last four digits («*** ۴۳۹۱») with «دریافت کد», no number field',
      st == 200 and masked(PH['sms']) in page and 'name="known"' in page and 'id="tsa_phone"' not in page
      and not in_full(PH['sms'], page), str(st))
st, h, j = ajax(pub, '/signup/send', {'csrf_token': pub.csrf(page), 'known': '1', 'phone': '', 'next': '/my'})
check('Q16 «دریافت کد» sends the code to the invited number; the answer shows it masked',
      j.get('state') == 'code' and j.get('phone_fa') == masked(PH['sms']) and last_code(PH['sms']), str(j)[:160])
st, h, j = ajax(pub, '/signup/verify', {'csrf_token': pub.csrf(page), 'code': last_code(PH['sms']), 'next': '/my'})
st2, loc2, _ = pub.req('/my')
check('Q17 after the code the session is an ordinary full session (/my opens)', j.get('ok') and st2 == 200, '%s %s' % (j, st2))
logout(pub)

# ================================================================ 4. device binding: the same browser goes on, another gets a code
st, _, page = pub.req('/invite/%s' % T_SMS)
check('D01 the bound browser, signed out: the welcome says «ادامه»', st == 200 and '>ادامه<' in page, str(st))
n = sms_count(PH['sms'])
st, loc, _ = pub.req('/invite/%s/accept' % T_SMS, {'csrf_token': pub.csrf(page), 'welcome': '1'})
check('D02 ...and goes on without a code (scoped again: a phone-only account the flow made)', st == 303
      and sms_count(PH['sms']) == n and path_of(loc) == '/invite/' + T_SMS, loc)
st, loc, _ = pub.req(path_of(loc))
check('D03 ...to its player', st in (302, 303) and '/take/' in loc, loc)
# the scoped session taken to another website (eot.ir): destroyed there at once
sid = next((c.value for c in pub.jar if c.name == 'session_id'), '')
st0, _h0, p0 = raw(client(), '/take/%s' % TOK1, headers={'Cookie': 'session_id=%s' % sid})
st, h, _ = raw(client(EOT), '/my', headers={'Cookie': 'session_id=%s' % sid})
check('O01 a scoped session seen on eot.ir is signed out at once: the page answers as to a visitor (303 to itself)',
      st0 == 200 and st == 303 and path_of(h.get('Location', '')) == '/my', '%s %s %s' % (st0, st, h.get('Location')))
st2, _h2, p2 = raw(client(), '/take/%s' % TOK1, headers={'Cookie': 'session_id=%s' % sid})
check('O02 ...the session is destroyed: back on talentsearch.ir the same cookie opens nothing', st2 != 200 or 'ts-qform' not in p2,
      str(st2))
st3, _h3, _p3 = raw(client(EOT), '/web/dataset/call_kw', headers={'Cookie': 'session_id=%s' % sid})
check('O03 eot.ir pages work for that browser as for any visitor afterwards', st3 != 500, str(st3))
logout(pub)
shell("env.cr.execute(\"update ts_signup_otp set create_date = create_date - interval '2 hours'\"); env.cr.commit()")
other_browser = client()
st, _, page = other_browser.req('/invite/%s' % T_SMS)
n = sms_count(PH['sms'])
st, loc, _ = other_browser.req('/invite/%s/accept' % T_SMS, {'csrf_token': other_browser.csrf(page), 'welcome': '1'})
check('D04 another browser gets no session: a code goes to the invited number', st == 303 and path_of(loc).startswith('/signup?step=code')
      and sms_count(PH['sms']) == n + 1, loc)
st, page = get(other_browser, path_of(loc))
check('D05 «برای ادامه، کدی به *** ۴۳۹۱ فرستادیم»: the last four digits only, never in full, nothing to type but the code',
      st == 200 and 'برای ادامه، کدی به' in page and masked(PH['sms']) in page and not in_full(PH['sms'], page)
      and 'ویرایش شماره' not in page and 'id="tsa_code"' in page, str(st))
st, h, j = ajax(other_browser, '/signup/verify', {'csrf_token': other_browser.csrf(page), 'code': last_code(PH['sms']),
                                                  'next': '/invite/%s' % T_SMS})
check('D06 after the code it goes on', j.get('ok') and j.get('redirect') == '/invite/%s' % T_SMS, str(j)[:160])
st, loc, _ = other_browser.req('/invite/%s' % T_SMS)
check('D07 ...to the same invitation\'s player', st in (302, 303) and '/take/' in loc, loc)
other_browser.req('/web/session/logout', {'csrf_token': other_browser.csrf(other_browser.req('/my')[2])})
shell("env.cr.execute(\"update ts_signup_otp set create_date = create_date - interval '2 hours'\"); env.cr.commit()")
ob = client()
st, _, page = ob.req('/invite/%s' % T_SMS)
st, loc, _ = ob.req('/invite/%s/accept' % T_SMS, {'csrf_token': ob.csrf(page), 'welcome': '1'})
st, page = get(ob, path_of(loc))
check('D08 the masked-code page offers «شمارهٔ دیگری دارم» (the ordinary sign-in)', st == 200 and 'signup?other=1' in page
      and 'شمارهٔ دیگری دارم' in page, str(st))
st, page = get(ob, '/signup?other=1&next=/invite/%s' % T_SMS)
check('D09 ...which shows the number field and never the invited number', st == 200 and 'id="tsa_phone"' in page
      and masked(PH['sms']) not in page and not in_full(PH['sms'], page), str(st))
st, h, j = ajax(ob, '/signup/send', {'csrf_token': ob.csrf(page), 'phone': PH['other'], 'next': '/invite/%s' % T_SMS})
st, h, j = ajax(ob, '/signup/verify', {'csrf_token': ob.csrf(page), 'code': last_code(PH['other']) or '000000',
                                       'next': '/invite/%s' % T_SMS})
info = q("a = env['ts.assignment'].sudo().search([('token', '=', '%s')]); print('OWN', a.user_id.login)" % T_SMS)
check('D10 signing in with another number accepts nothing for it: the invitation stays with the invited account',
      j.get('ok') and ('OWN %s' % PH['sms']) in info, '%s %s' % (str(j)[:80], info.strip()[-40:]))
ob.req('/web/session/logout', {'csrf_token': ob.csrf(ob.req('/my')[2])})
# «این دستگاه شخصی من است» unticked: a browser-session cookie, 12 hours on the server; the binding ends with the invitation
dv = client()
st, h, _ = raw(dv, '/i/%s/%s' % (SHORT_D, DLV_D))
st, page = get(dv, path_of(h.get('Location', '')))
st, h, _ = raw(dv, '/invite/%s/accept' % T_DEV, {'csrf_token': dv.csrf(page), 'welcome': '1', 'share': '1', 'd': DLV_D})
dck = [c for c in cookies(h) if c.startswith('ts_dev=')]
info = q("from odoo import fields\na = env['ts.assignment'].sudo().search([('token', '=', '%s')])\n"
         "print('DV', round((a.device_until - fields.Datetime.now()).total_seconds() / 3600, 1))" % T_DEV)
hours = float((re.search(r'DV ([\d.]+)', info) or [0, '0'])[1])
check('D11 unticked: straight in, the browser cookie is a session cookie (no Max-Age, no Expires) and the server side ends '
      'within 12 hours', st == 303 and '/take/' in h.get('Location', '') and dck and 'max-age' not in dck[0].lower()
      and 'expires' not in dck[0].lower() and 11 < hours <= 12.01, '%s %s %s' % (st, str(dck)[:80], hours))
logout(dv)
st, _, page = dv.req('/invite/%s' % T_DEV)
n = sms_count(PH['dev'])
st, loc, _ = dv.req('/invite/%s/accept' % T_DEV, {'csrf_token': dv.csrf(page), 'welcome': '1'})
check('D12 ...the same browser session goes on without a code', st == 303 and path_of(loc) == '/invite/' + T_DEV
      and sms_count(PH['dev']) == n, loc)
q("from odoo import fields\na = env['ts.assignment'].sudo().search([('token', '=', '%s')])\n"
  "for t in a.ts_battery_attempts() or a.attempt_id:\n    t.write({'state': 'done', 'submitted_at': fields.Datetime.now()})\n"
  "env.cr.commit()" % T_DEV)
logout(dv)
st, _, page = dv.req('/invite/%s' % T_DEV)
n = sms_count(PH['dev'])
st, loc, _ = dv.req('/invite/%s/accept' % T_DEV, {'csrf_token': dv.csrf(page), 'welcome': '1'})
check('D13 once the invitation is finished the binding has ended: a code to the invited number', st == 303
      and path_of(loc).startswith('/signup?step=code') and sms_count(PH['dev']) == n + 1, loc)

# ================================================================ 5. a signed-in account that is not the invited number
oc = client()
assert oc.login(L['other'], pw[L['other']])
st, _, page = oc.req('/invite/%s' % T_MIS)
check('M01 another account: one clear notice with the invited number (last four digits) and one action «خروج و ورود با شمارهٔ دعوت‌شده»',
      st == 200 and masked(PH['mis']) in page and 'خروج و ورود با شمارهٔ دعوت‌شده' in page and 'موافقم و شروع می‌کنم' not in page
      and page.count('ts-btn--primary') == 1 and not in_full(PH['mis'], page), str(st))
st, loc, _ = oc.req('/invite/%s/accept' % T_MIS, {'csrf_token': oc.csrf(page), 'welcome': '1', 'share': '1'})
info = q("a = env['ts.assignment'].sudo().search([('token', '=', '%s')]); print('MIS', bool(a.user_id))" % T_MIS)
check('M02 a POST from that account accepts nothing', 'MIS False' in info and st == 303, '%s %s' % (st, info.strip()[-20:]))
st, loc, _ = oc.req('/invite/%s' % T_SMS)
check('M03 an invitation accepted by someone else: the explained link 404 (same as an unknown token; sign out, sign in)',
      st == 404 and 'id="ts-link-404"' in _ and 'خروج و ورود با شمارهٔ دیگر' in _, str(st))

# ================================================================ 6. e-mail, a typed number, a plain link
ec = client()
st, page = get(ec, '/invite/%s?d=%s' % (T_EMAIL, DLV_E1))
st, loc, _ = ec.req('/invite/%s/accept' % T_EMAIL, {'csrf_token': ec.csrf(page), 'welcome': '1', 'share': '1', 'personal': '1',
                                                    'd': DLV_E1})
info = q("a = env['ts.assignment'].sudo().search([('token', '=', '%s')]); print('EM', a.user_id.login, a.attempt_id.state, a.ts_account_made)" % T_EMAIL)
check('E01 the e-mail\'s own link (with its secret) to an address without an account: one tap, the account made, for this '
      'invitation only', st == 303 and '/take/' in loc and ('EM %s in_progress True' % EMAIL) in info, '%s %s' % (loc, info.strip()[-60:]))
st, loc, _ = ec.req('/my')
st2, page = get(ec, '/my')
check('E02 ...and /my asks for the sign-in (no number known yet: the number field)', st == 303 and 'id="tsa_phone"' in page, '%s' % st)
# HIGH 2: the account is no longer «made moments ago»: a code for a new number never writes it onto that account
q("env.cr.execute(\"UPDATE res_users SET create_date = now() - interval '2 hours' WHERE login = '%s'\"); env.cr.commit()" % EMAIL)
st, page = get(ec, '/signup?next=/my')
ajax(ec, '/signup/send', {'csrf_token': ec.csrf(page), 'phone': PH['emq'], 'next': '/my'})
st, h, j = ajax(ec, '/signup/verify', {'csrf_token': ec.csrf(page), 'code': last_code(PH['emq']) or '000000', 'next': '/my'})
info = q("U = env['res.users'].sudo().with_context(active_test=False); e = U.search([('login', '=', '%s')]); p = U.search([('login', '=', '%s')]); "
         "a = env['ts.assignment'].sudo().search([('token', '=', '%s')]); "
         "print('HQ', bool(e.partner_id.ts_phone), bool(p), p != e, a.user_id == e)" % (EMAIL, PH['emq'], T_EMAIL))
check('E07 an e-mail-scoped session cannot attach a new number to a pre-existing account: the code signs into a new phone '
      'account, the invitation stays where it is', j.get('ok') and 'HQ False True True True' in info
      and j.get('redirect') == '/my/invitation-elsewhere', '%s %s' % (str(j)[:100], info.strip()[-30:]))
st, page = get(ec, '/my/invitation-elsewhere')
check('E07b ...and one calm page says so (the invitation stays in the account of «ts***@example.invalid»)', st == 200
      and 'دعوت در حساب دیگری است' in page and 'ts***@example.invalid' in page and page.count('ts-btn--primary') == 1, str(st))
e9 = client()
st, _, page = e9.req('/invite/%s' % T_EMAIL2)
st, loc, _ = e9.req('/invite/%s/accept' % T_EMAIL2, {'csrf_token': e9.csrf(page), 'welcome': '1', 'share': '1'})
info = q("a = env['ts.assignment'].sudo().search([('token', '=', '%s')]); print('E9', bool(a.user_id))" % T_EMAIL2)
check('E09 the link the panel copied of an e-mail invitation without a number: the ordinary sign-in, never a session',
      st in (302, 303) and path_of(loc) == '/signup?next=/invite/%s' % T_EMAIL2 and 'E9 False' in info, loc)
e8 = client()
st, page = get(e8, '/invite/%s?d=%s' % (T_EMAIL2, DLV_E2))
st, loc, _ = e8.req('/invite/%s/accept' % T_EMAIL2, {'csrf_token': e8.csrf(page), 'welcome': '1', 'share': '1', 'd': DLV_E2})
st, page = get(e8, '/signup?next=/my')
ajax(e8, '/signup/send', {'csrf_token': e8.csrf(page), 'phone': PH['emr'], 'next': '/my'})
st, h, j = ajax(e8, '/signup/verify', {'csrf_token': e8.csrf(page), 'code': last_code(PH['emr']) or '000000', 'next': '/my'})
info = q("e = env['res.users'].sudo().search([('login', '=', '%s')]); print('HR', e.partner_id.ts_phone)" % EMAIL2)
check('E08 the only exception: the account made moments ago for this invitation, holding nothing else, gets the number',
      j.get('ok') and ('HR %s' % PH['emr']) in info and j.get('redirect') != '/my/invitation-elsewhere',
      '%s %s' % (str(j)[:80], info.strip()[-30:]))
mc = client()
st, _, page = mc.req('/invite/%s' % T_MANUAL)
n = sms_count(PH['manual'])
st, loc, _ = mc.req('/invite/%s/accept' % T_MANUAL, {'csrf_token': mc.csrf(page), 'welcome': '1', 'share': '1', 'personal': '1'})
check('E03 a link the panel copied, with a number on the invitation: a code to that number first (masked)',
      st == 303 and path_of(loc).startswith('/signup?step=code') and sms_count(PH['manual']) == n + 1, loc)
st, page = get(mc, path_of(loc))
st, h, j = ajax(mc, '/signup/verify', {'csrf_token': mc.csrf(page), 'code': last_code(PH['manual']), 'next': '/invite/%s' % T_MANUAL})
info = q("a = env['ts.assignment'].sudo().search([('token', '=', '%s')]); print('MAN', a.user_id.login, a.attempt_id.state, a.welcome_version or '-', bool(a.device_until))" % T_MANUAL)
check('E04 ...then the invitation is accepted with the consent of the first tap (and bound to this browser)',
      j.get('ok') and '/take/' in (j.get('redirect') or '') and ('MAN %s in_progress TS-CONSENT' % PH['manual']) in info
      and re.search(r'MAN %s in_progress TS-CONSENT\S* True' % PH['manual'], info), '%s %s' % (j, info.strip()[-60:]))
lc = client()
st, _, page = lc.req('/invite/%s' % T_LINK)
st, loc, _ = lc.req('/invite/%s/accept' % T_LINK, {'csrf_token': lc.csrf(page), 'welcome': '1'})
check('E05 a plain link (no number, no address): the ordinary sign-in first, as before', st in (302, 303)
      and path_of(loc) == '/signup?next=/invite/%s' % T_LINK, loc)
dc = client()
st, _, page = dc.req('/invite/%s?decline=1' % T_DEC)
st, loc, _ = dc.req('/invite/%s/decline' % T_DEC, {'csrf_token': dc.csrf(page)})
info = q("a = env['ts.assignment'].sudo().search([('token', '=', '%s')]); print('DEC', a.state, bool(a.user_id))" % T_DEC)
check('E06 «نمی‌خواهم شرکت کنم» works without an account and ties the invitation to none', 'DEC declined False' in info, info.strip()[-30:])

# ================================================================ 7. minors: one screen
yc = client()
assert yc.login(L['minor'], pw[L['minor']])
st, _, page = yc.req('/invite/%s' % T_MINOR)
check('N01 a minor client: the guardian tick and the child\'s own button «من هم موافقم» on the one screen',
      st == 200 and 'name="guardian_confirm"' in page and 'من هم موافقم' in page and 'موافقم و شروع می‌کنم' not in page, str(st))
st, loc, _ = yc.req('/invite/%s/accept' % T_MINOR, {'csrf_token': yc.csrf(page), 'welcome': '1', 'share': '1'})
check('N02 without the tick the screen comes back with one line', st == 303 and 'error=guardian' in loc, loc)
st, loc, _ = yc.req('/invite/%s/accept' % T_MINOR, {'csrf_token': yc.csrf(page), 'welcome': '1', 'share': '1', 'guardian_confirm': '1'})
st2, _, p2 = yc.req(path_of(loc)) if '/take/' in loc else (0, '', '')
info = q("a = env['ts.assignment'].sudo().search([('token', '=', '%s')]); R = env['ts.consent.record'].sudo().search([('attempt_id', '=', a.attempt_id.id)]); "
         "print('MIN', a.attempt_id.state, ','.join(sorted(R.mapped('kind'))))" % T_MINOR)
check('N03 with it: straight to the questions, never a second consent screen; the ledger has guardian + assent + service + share',
      '/take/' in loc and st2 == 200 and 'consent_service' not in p2 and 'assent_ok' not in p2
      and re.search(r'MIN in_progress assent,guardian,service', info), '%s %s' % (loc, info.strip()[-80:]))
if T_CHILD != '-':
    st, _, page = yc.req('/invite/%s' % T_CHILD)
    check('N04 BAT-CHILD-1 for a minor client: the parent\'s one tick, the ordinary button, no child assent',
          st == 200 and 'name="guardian_confirm"' in page and 'موافقم و شروع می‌کنم' in page and 'من هم موافقم' not in page, str(st))
    st, loc, _ = yc.req('/invite/%s/accept' % T_CHILD, {'csrf_token': yc.csrf(page), 'welcome': '1', 'share': '1', 'guardian_confirm': '1'})
    st2, _, p2 = yc.req(path_of(loc)) if '/take/' in loc else (0, '', '')
    check('N05 ...and the first child instrument opens without another consent page', st2 == 200 and 'consent_service' not in p2, loc)
else:
    check('N04 BAT-CHILD-1 fixture', False, 'no BAT-CHILD-1 invitation could be made')

# ================================================================ 8. employment: company, position, timed line; fairness at the end
ac = client()
st, _, page = ac.req('/invite/%s' % T_EMP)
check('H01 a candidate: the company «برای موقعیت «…»», «روی کامپیوتر بهتر است (بخش زمان‌دار)», no fairness questions',
      st == 200 and 'شرکت onb2 وب' in page and 'برای موقعیت «' in page and 'روی کامپیوتر بهتر است (بخش زمان‌دار)' in page
      and 'name="ts_gender"' not in page, str(st))
oc2 = client()
assert oc2.login(L['other'], pw[L['other']])
st, page = get(oc2, '/my/assessments/battery/%s' % FAIR_ID)
check('H02 after the last part: the two optional questions once, before the feedback, with «رد شدن»',
      st == 200 and 'name="ts_gender"' in page and 'رد شدن' in page and 'بازخورد شما' not in page, '%s %s' % (st, FAIR_STATE))
st, loc, _ = oc2.req('/my/assessments/battery/%s/about/save' % FAIR_ID, {'csrf_token': oc2.csrf(page), 'skip': '1', 'ts_gender': 'male'})
info = q("a = env['ts.assignment'].sudo().browse(%s); print('FAIR', a.ts_gender or '-', a.ts_fair_asked)" % FAIR_ID)
check('H03 «رد شدن» stores nothing and the questions are not asked again', 'FAIR - True' in info and st == 303, info.strip()[-30:])
st, page = get(oc2, '/my/assessments/battery/%s' % FAIR_ID)
check('H04 the feedback page opens directly afterwards', st == 200 and 'name="ts_gender"' not in page, str(st))

# ================================================================ 8b. a scoped session drives an HR battery with timed tasks


def csrf_any(page):
    m_ = re.search(r'name="csrf_token" value="([^"]+)"', page) or re.search(r'csrf_token["\']?\s*:\s*["\']([^"\']+)', page)
    return m_.group(1) if m_ else ''


hc = client()
st, h, _ = raw(hc, '/i/%s/%s' % (SHORT_H, DLV_H))
st, page = get(hc, path_of(h.get('Location', '')))
st, h, _ = raw(hc, '/invite/%s/accept' % T_HR, {'csrf_token': hc.csrf(page), 'welcome': '1', 'share': '1', 'personal': '1',
                                                  'd': DLV_H})
loc = h.get('Location', '')
info = q("a = env['ts.assignment'].sudo().search([('token', '=', '%s')]); "
         "print('HRT', '|'.join(t.access_token for t in a.ts_battery_attempts()), a.id)" % T_HR)
mh = re.search(r'HRT (\S+) (\d+)', info)
H1, H2 = (mh.group(1).split('|') + ['x', 'x'])[:2] if mh else ('x', 'x')
HAID = mh.group(2) if mh else '0'
check('T01 the candidate\'s own SMS link: one tap, a session scoped to this invitation, straight to its first part',
      st == 303 and ('/take/%s' % H1) in loc, '%s %s' % (st, loc))
st, h, page = raw(hc, '/take/%s' % H1)
check('T00 a scoped page never starts the website bus (no bus_info in the session info: no /websocket, no reconnect loop)',
      st == 200 and 'ts-qform' in page and 'bus_info' not in page, str(st))
st_n, normal = get(oc2, '/my')
check('T00b ...while an ordinary signed-in page carries it (the check above is not vacuous)', st_n == 200 and 'bus_info' in normal,
      str(st_n))
items = re.findall(r'name="q_(\d+)"', page)
st, h, j = ajax(hc, '/take/%s/answer' % H1, {'csrf_token': hc.csrf(page), 'item': items[0] if items else '0', 'value': '3'})
check('T02 a Likert answer (the autosave POST) in the scoped session', st == 200 and j.get('ok'), '%s %s' % (st, str(j)[:80]))
ids = shell("t = env['ts.attempt'].sudo().search([('access_token', '=', '%s')]); print('ITEMS', ','.join(str(i.id) for i in t.active_items()))" % H1)
hi = re.search(r'ITEMS ([\d,]+)', ids)
hids = hi.group(1).split(',') if hi else []
for k in range(0, len(hids), 5):
    hc.req('/take/%s/page' % H1, [('csrf_token', hc.csrf(page)), ('page', str(k // 5 + 1)), ('go', 'next')]
           + [('q_%s' % i, '3') for i in hids[k:k + 5]])
st, page = get(hc, '/take/%s/review' % H1)
st, loc, _ = hc.req('/take/%s/submit' % H1, {'csrf_token': hc.csrf(page)})
check('T03 the questionnaire part is sent in the scoped session and the battery moves on', st in (302, 303)
      and ('/next' in loc or '/take/' in loc), loc)
st, page = get(hc, '/take/%s' % H2)
tcsrf = csrf_any(page)
check('T04 the timed-task player opens in the scoped session', st == 200 and 'tst-player' in page and tcsrf, str(st))
codes, fin = [], {}
for i in range(3):
    st, _h, rb = raw(hc, '/take/%s/task/start' % H2, {'csrf_token': tcsrf, 'i': str(i)})
    j = json.loads(rb) if st == 200 else {}
    codes.append(st)
    for idx in range(len(j.get('items', []))):
        st, _h, _rb = raw(hc, '/take/%s/task/answer' % H2, {'csrf_token': tcsrf, 'i': str(i), 'idx': str(idx), 'c': '0', 'rt': '3500'})
        codes.append(st)
    st, _h, rb = raw(hc, '/take/%s/task/finish' % H2, {'csrf_token': tcsrf, 'i': str(i), 'focus_lost': '0'})
    codes.append(st)
    fin = json.loads(rb) if st == 200 else {}
check('T05 /take/<t>/task/start, /answer and /finish succeed in the scoped session; the last block returns the battery result',
      all(c in (200, 409) for c in codes) and (fin.get('url') or '').startswith('/my/assessments/battery/%s' % HAID),
      '%s %s' % (sorted(set(codes)), str(fin)[:80]))
st, _h, _rb = raw(hc, '/take/%s/task/start' % FAIR_TASK, {'csrf_token': tcsrf, 'i': '0'})
check('T06 another person\'s task token from the scoped session: refused (403)', st in (403, 404), str(st))
st, _, ypage = yc.req('/my')
st2, _h, _rb = raw(yc, '/take/%s/task/start' % H2, {'csrf_token': csrf_any(ypage), 'i': '0'})
check('T07 ...and another signed-in account cannot drive this candidate\'s task (403/404)', st2 in (403, 404), str(st2))

# ================================================================ 9. short links: rate limit
shell("env['ir.config_parameter'].sudo().set_str('ts_onboard.short_per_minute', '5'); env['ts.rate.hit'].sudo().search([]).unlink(); env.cr.commit()")
rl = client()
codes = [rl.req('/i/%s' % SHORT)[0] for _ in range(6)]
st, h, page = raw(rl, '/j/abcdabcdabcd')
check('R01 short-link lookups are limited per address: then a polite 429 page with Retry-After',
      codes[:5] == [302] * 5 and codes[5] == 429 and st == 429 and 'کمی صبر کنید' in page and h.get('Retry-After') == '60', str(codes + [st]))
st, _, _ = raw(rl, '/c/nothing-here')
check('R02 the open class link /c/ has its own, larger allowance (a whole class opens it from one school network)',
      st == 404, str(st))
shell("ICP = env['ir.config_parameter'].sudo(); ICP.set_str('ts_onboard.invite_per_minute', '3'); "
      "ICP.set_str('ts_onboard.campaign_per_minute', '2'); env['ts.rate.hit'].sudo().search([]).unlink(); env.cr.commit()")
inv = [raw(rl, '/invite/%s' % ('y' * 43))[0] for _ in range(4)]
check('R03 /invite/ lookups are limited per address too, and unknown tokens count (404 404 404, then 429)',
      inv == [404, 404, 404, 429], str(inv))
cc = [raw(rl, '/c/nothing-here')[0] for _ in range(3)]
check('R04 /c/ lookups are limited with their own allowance', cc == [404, 404, 429], str(cc))
shell("ICP = env['ir.config_parameter'].sudo(); ICP.set_str('ts_onboard.short_per_minute', '30'); "
      "ICP.set_str('ts_onboard.invite_per_minute', '60'); ICP.set_str('ts_onboard.campaign_per_minute', '120'); "
      "env['ts.rate.hit'].sudo().search([]).unlink(); env.cr.commit()")

# ================================================================ 10. test first: start, guest attempt, gate, claim
g = client()
st, h, page = raw(g, '/')
check('P01 home: the primary action is «شروع سنجهٔ رایگان» to /start, with «حدود N دقیقه · بدون ثبت‌نام برای شروع · نتیجه فقط برای خودتان»',
      st == 200 and re.search(r'href="/start"[^>]*>شروع سنجهٔ رایگان', page) and ('حدود %s دقیقه' % SMIN.translate(FA)) in page
      and 'بدون ثبت‌نام برای شروع' in page, str(st))
hero = page.split('id="tso-hero-links"', 1)[1][:900] if 'id="tso-hero-links"' in page else ''
check('P01b ...then three quiet text links for organisations (centres, companies, schools), no second hero button',
      'برای مراکز مشاوره' in hero and 'برای شرکت‌ها و استخدام' in hero and 'href="/schools">برای مدرسه‌ها' in hero
      and page.split('id="tso-hero-start"', 1)[1].split('</div>', 1)[0].count('ts-btn') == 0, hero[:120])
st, h, page = raw(g, '/start')
check('P02 /start: the starter, statements and minutes, the promise, the age button, «کمتر از ۱۸ سال دارم», an unticked research box',
      st == 200 and SCODE == 'inventory_002' and ('%s جمله' % SITEMS.translate(FA)) in page
      and 'پاسخ‌ها فقط برای خودتان است؛ در پایان با شمارهٔ موبایل نتیجه را می‌بینید و نگه می‌دارید.' in page
      and '۱۸ سال یا بیشتر دارم؛ موافقم و شروع می‌کنم' in page and 'href="/start/under-18"' in page
      and re.search(r'name="consent_research" value="1"/>', page) and 'checked' not in re.search(r'<input type="checkbox" name="consent_research"[^>]*>', page).group(0), str(st))
st, page = get(g, '/start/under-18')
check('P03 under 18: no guest attempt; the school or counselor path, a link to /schools', st == 200 and 'href="/schools"' in page
      and 'action="/start/' not in page, str(st))
st, page = get(g, '/assessments/%s' % SLUG)
check('P04 the detail page\'s «شروع سنجه» goes to the start screen, not to a sign-in', st == 200
      and ('href="/start/%s"' % urllib.parse.quote(SLUG)) in page and '/signup?next=/assessments' not in page, str(st))
st, page = get(g, '/assessments?all=1')
check('P04b the catalog card of the starter opens its start screen («شروع بدون ثبت‌نام»)', st == 200
      and ('href="/start/%s"' % SLUG) in page and 'شروع بدون ثبت‌نام' in page, str(st))
st, page = get(g, '/start')
st, h, _ = raw(g, '/start/%s/go' % SLUG, {'csrf_token': g.csrf(page), 'consent_research': '1'})
gck = [c for c in cookies(h) if c.startswith('ts_guest=')]
GTOKEN = gck[0].split(';')[0].split('=', 1)[1] if gck else 'none'
LOCS.append(h.get('Location', ''))
check('P05 the tap starts a guest attempt: /start/q, a signed HttpOnly SameSite=Lax cookie, no token in the address',
      st == 303 and path_of(h.get('Location', '')) == '/start/q' and gck and 'HttpOnly' in gck[0] and 'SameSite=Lax' in gck[0]
      and GTOKEN.split('.')[0] not in h.get('Location', ''), '%s %s' % (st, h.get('Location')))
info = q("t = env['ts.attempt'].sudo().search([('ts_guest', '=', True)], order='id desc', limit=1); print('GA', t.id, t.user_id._is_public(), t.state, "
         "t.consent_research, bool(t.workspace_id), len(t.ts_guest_hash or ''), t.access_token)")
gm = re.search(r'GA (\d+) True in_progress True False 64 (\w+)', info)
check('P06 the guest attempt: owned by the public user, consent and research recorded, no panel, only the digest stored', gm, info.strip()[-120:])
GID, GACCESS = gm.groups() if gm else ('0', 'none')
st, h, page = raw(g, '/start/q')
check('P07 the same player (focus header), autosave address /start/q/answer, no token anywhere in the page',
      st == 200 and 'ts-qform' in page and 'data-answer-url="/start/q/answer"' in page and GACCESS not in page
      and GTOKEN.split('.')[0] not in page and h.get('Referrer-Policy') == 'no-referrer', str(st))
items = re.findall(r'name="q_(\d+)"', page)
first = sorted(set(items), key=items.index)
st, h, j = ajax(g, '/start/q/answer', {'csrf_token': g.csrf(page), 'item': first[0], 'value': '4'})
check('P08 autosave answers JSON', j.get('ok') and j.get('answered') == 1, str(j)[:80])
allitems = q("t = env['ts.attempt'].sudo().browse(%s); print('IT', ','.join(str(i.id) for i in t.active_items()))" % GID)
ids = re.search(r'IT ([\d,]+)', allitems).group(1).split(',')
for k in range(0, len(ids), 10):
    g.req('/start/q/page', [('csrf_token', g.csrf(page)), ('page', str(k // 10 + 1)), ('go', 'next')] + [('q_%s' % i, '3') for i in ids[k:k + 10]])
st, page = get(g, '/start/q/review')
check('P09 the review says the result is seen with the mobile number', st == 200 and 'با شمارهٔ موبایل نتیجه را می‌بینید' in page, str(st))
st, loc, _ = g.req('/start/q/submit', {'csrf_token': g.csrf(page)})
LOCS.append(loc)
check('P10 sending leads to the result gate', st == 303 and path_of(loc) == '/start/result', loc)
st, h, page = raw(g, '/start/result')
check('P11 the gate: «نتیجه‌تان آماده است.» with the mobile sign-in inline and the gate sentence',
      st == 200 and 'نتیجه‌تان آماده است.' in page and 'شماره‌تان را بزنید تا نتیجه را ببینید و برای همیشه داشته باشید.' in page
      and 'id="tsa_phone"' in page and GTOKEN.split('.')[0] not in page, str(st))
st, h, j = ajax(g, '/signup/send', {'csrf_token': g.csrf(page), 'phone': PH['guest'], 'next': '/start/result', 'personal_shown': '1', 'personal': '1'})
st, h, j = ajax(g, '/signup/verify', {'csrf_token': g.csrf(page), 'code': last_code(PH['guest']), 'next': '/start/result'})
drop = [c for c in cookies(h) if c.startswith('ts_guest=')]
check('P12 the code asked for from the gate claims the attempt and opens its report; the guest cookie is dropped',
      j.get('ok') and (j.get('redirect') or '').startswith('/my/assessments/%s?' % GID) and drop and 'Max-Age=0' in drop[0], str(j)[:120])
info = q("t = env['ts.attempt'].sudo().browse(%s); print('CL', t.user_id.login, t.ts_guest, bool(t.ts_guest_hash), bool(t.ts_guest_claimed_at))" % GID)
check('P13 the attempt now belongs to the account; the browser token is invalid', ('CL %s False False True' % PH['guest']) in info, info.strip()[-60:])
st, page = get(g, j.get('redirect') or '/my')
check('P14 the report: «نامی که روی گزارش بیاید (اختیاری)», «سنجهٔ بعدی», «فرستادن نتیجه برای مشاورتان»',
      st == 200 and 'نامی که روی گزارش بیاید (اختیاری)' in page and 'سنجهٔ بعدی' in page and 'فرستادن نتیجه برای مشاورتان' in page, str(st))
st, loc, _ = g.req('/my/assessments/%s/name' % GID, {'csrf_token': g.csrf(page), 'name': 'سارا آزمایشی'})
info = q("u = env['res.users'].search([('login', '=', '%s')]); print('NM', u.partner_id.ts_name_unknown, u.name)" % PH['guest'])
check('P15 the optional name is the person\'s own entry: it names the account that had none', 'NM False سارا آزمایشی' in info, info.strip()[-40:])
st, page = get(g, '/start')
st, loc, _ = g.req('/start/%s/go' % SLUG, {'csrf_token': g.csrf(page)})
check('P16 a signed-in visitor goes straight into an ordinary attempt (no consent page)', st == 303 and '/take/' in loc, loc)
st, _, p2 = g.req(path_of(loc))
check('P17 ...whose player opens directly', st == 200 and 'consent_service' not in p2, str(st))
st, h, j = ajax(g, '/web/session/logout', {'csrf_token': g.csrf(p2)})

# cross-token isolation: a forged or a spent browser token reaches nothing; another account never opens a guest attempt
xc = client()
forged = GTOKEN.split('.')[0] + '.' + '0' * 32
st, h, _ = raw(xc, '/start/q', headers={'Cookie': 'ts_guest=%s' % forged})
check('X01 a forged guest cookie (right token, wrong signature) reaches no attempt: back to /start',
      st in (302, 303) and path_of(h.get('Location', '')) == '/start', '%s %s' % (st, h.get('Location')))
st, h, _ = raw(xc, '/start/result', headers={'Cookie': 'ts_guest=%s' % GTOKEN})
check('X02 the cookie of a claimed attempt is spent: its gate and result do not open again from that browser token',
      st in (302, 303) and path_of(h.get('Location', '')) == '/start', '%s %s' % (st, h.get('Location')))
check('X03 another signed-in account cannot open the claimed attempt\'s player or report',
      oc.req('/take/%s' % GACCESS)[0] in (403, 404) and oc.req('/my/assessments/%s' % GID)[0] in (403, 404))
st, h, _ = raw(xc, '/start/q', headers={'Cookie': 'ts_guest=%s' % GTOKEN.replace('.', '')})
check('X04 a malformed cookie reaches nothing either', st in (302, 303) and path_of(h.get('Location', '')) == '/start', str(st))

# keep both: the same person claims a second result of the same instrument
g2 = client()
st, page = get(g2, '/start')
st, loc, _ = g2.req('/start/%s/go' % SLUG, {'csrf_token': g2.csrf(page)})
info = q("t = env['ts.attempt'].sudo().search([('ts_guest', '=', True)], order='id desc', limit=1)\nfor it in t.active_items(): t.save_answer(it.id, 2)\n"
         "t.action_submit(); env.cr.commit(); print('G2', t.id)")
G2 = re.search(r'G2 (\d+)', info).group(1)
st, page = get(g2, '/start/result')
shell("env.cr.execute(\"update ts_signup_otp set create_date = create_date - interval '2 hours'\"); env.cr.commit()")
ajax(g2, '/signup/send', {'csrf_token': g2.csrf(page), 'phone': PH['guest'], 'next': '/start/result'})
st, h, j = ajax(g2, '/signup/verify', {'csrf_token': g2.csrf(page), 'code': last_code(PH['guest']) or '000000', 'next': '/start/result'})
info = q("u = env['res.users'].search([('login', '=', '%s')]); print('BOTH', env['ts.attempt'].sudo().search_count([('user_id', '=', u.id), "
         "('instrument_id.code', '=', 'inventory_002'), ('state', '=', 'done')]))" % PH['guest'])
check('P18 a second claim of the same instrument keeps both results', j.get('ok') and 'BOTH 2' in info, '%s %s' % (j, info.strip()[-20:]))

# limits: one open guest attempt per browser, three new ones per address and hour
g3 = client()
st, page = get(g3, '/start')
st, loc, _ = g3.req('/start/%s/go' % SLUG, {'csrf_token': g3.csrf(page)})
n1 = q("print('N', env['ts.attempt'].sudo().search_count([('ts_guest', '=', True)]))")
st, loc2, _ = g3.req('/start/%s/go' % SLUG, {'csrf_token': g3.csrf(page)})
n2 = q("print('N', env['ts.attempt'].sudo().search_count([('ts_guest', '=', True)]))")
check('L01 one open guest attempt per browser: a second tap goes back to it', path_of(loc2) == '/start/q' and n1.strip()[-6:] == n2.strip()[-6:],
      '%s %s %s' % (loc2, n1.strip()[-6:], n2.strip()[-6:]))
g4 = client()
st, page = get(g4, '/start')
st, h, p4 = raw(g4, '/start/%s/go' % SLUG, {'csrf_token': g4.csrf(page)})
check('L02 the fourth new guest attempt from one address within the hour gets the polite 429 page', st == 429 and 'کمی صبر کنید' in p4, str(st))
G3TOK = next((c.value for c in g3.jar if c.name == 'ts_guest'), '')
st_ok, _h, _p = raw(client(), '/start/q', headers={'Cookie': 'ts_guest=%s' % G3TOK})
st_bad, hb, _p = raw(client(), '/start/q', headers={'Cookie': 'ts_guest=%s.%s' % (G3TOK.rsplit('.', 1)[0], '0' * 32)})
check('X05 an open guest attempt is reached with its own signed cookie only: the same token with a forged signature gets nothing',
      G3TOK and st_ok == 200 and st_bad in (302, 303) and path_of(hb.get('Location', '')) == '/start', '%s %s' % (st_ok, st_bad))
shell("env['ir.config_parameter'].sudo().set_str('ts_onboard.answers_per_minute', '2'); "
      "env['ts.rate.hit'].sudo().search([('key', '=like', 'answer:%')]).unlink(); env.cr.commit()")
st, page = get(g3, '/start/q')
its = re.findall(r'name="q_(\d+)"', page)
ans = [ajax(g3, '/start/q/answer', {'csrf_token': g3.csrf(page), 'item': its[k % len(its)] if its else '0', 'value': '3'})[0]
       for k in range(3)]
check('L03 guest answers are limited per address (200 a minute; here 2): then 429', ans == [200, 200, 429], str(ans))
shell("env['ir.config_parameter'].sudo().set_str('ts_onboard.answers_per_minute', '200'); "
      "env['ts.rate.hit'].sudo().search([('key', '=like', 'answer:%')]).unlink(); env.cr.commit()")

# the claim needs the gate: a sign-in that did not come from this browser's gate never claims its attempt (shared computer)
shell("env['ts.rate.hit'].sudo().search([('key', '=like', 'guest:%')]).unlink(); env.cr.commit()")
g5 = client()
st, page = get(g5, '/start')
st, loc, _ = g5.req('/start/%s/go' % SLUG, {'csrf_token': g5.csrf(page)})
info = q("t = env['ts.attempt'].sudo().search([('ts_guest', '=', True)], order='id desc', limit=1)\nfor it in t.active_items(): t.save_answer(it.id, 2)\n"
         "t.action_submit(); env.cr.commit(); print('G5', t.id)")
G5 = re.search(r'G5 (\d+)', info).group(1)
st, page = get(g5, '/signup?next=/start/result')
ajax(g5, '/signup/send', {'csrf_token': g5.csrf(page), 'phone': PH['gate'], 'next': '/start/result'})
st, h, j = ajax(g5, '/signup/verify', {'csrf_token': g5.csrf(page), 'code': last_code(PH['gate']) or '000000', 'next': '/start/result'})
info = q("t = env['ts.attempt'].sudo().browse(%s); print('G5S', t.ts_guest, t.user_id._is_public())" % G5)
check('P19 a code asked for outside the gate (next=/start/result typed, the gate never shown in this session) claims nothing',
      j.get('ok') and 'G5S True True' in info and not (j.get('redirect') or '').startswith('/my/assessments/%s' % G5),
      '%s %s' % (str(j)[:80], info.strip()[-20:]))
st, page = get(g5, '/start/result')
check('P20 ...the gate, signed in, offers one explicit button to keep the result', st == 200 and 'action="/start/claim"' in page, str(st))
st, loc, _ = g5.req('/start/claim', {'csrf_token': g5.csrf(page)})
info = q("t = env['ts.attempt'].sudo().browse(%s); print('G5C', t.user_id.login, t.ts_guest)" % G5)
check('P21 ...and that button claims it', st == 303 and ('/my/assessments/%s' % G5) in loc and ('G5C %s False' % PH['gate']) in info,
      '%s %s' % (loc, info.strip()[-30:]))

# the 48-hour clean-up
out = shell("t = env['ts.attempt'].sudo().search([('ts_guest', '=', True)], order='id desc', limit=1)\nenv.flush_all()\n"
            "env.cr.execute(\"update ts_attempt set ts_guest_seen = now() - interval '49 hours' where id = %s\", [t.id])\n"
            "env.invalidate_all()\nn = env['ts.attempt']._cron_guest_cleanup()\nenv.cr.commit()\nprint('CLEAN', n, t.exists() and 'kept' or 'gone')")
check('C01 48 hours after the last activity an unclaimed guest attempt and its answers are gone', re.search(r'CLEAN [1-9]\d* gone', out), out.strip()[-40:])
st, loc, _ = g3.req('/start/q')
check('C02 ...and its browser starts again at /start', st in (302, 303) and path_of(loc) == '/start', loc)
check('C03 no address of this suite ever carried the guest token', not any(GTOKEN.split('.')[0] in (x or '') for x in LOCS) and len(LOCS) >= 3,
      len(LOCS))

# ================================================================ 11. funnel, eot.ir
# an invitation answered to the end through the player (the invitation path of the funnel: first answer, finished)
info = q("a = env['ts.assignment'].sudo().search([('token', '=', '%s')]); t = a.attempt_id; "
         "print('MT', t.access_token, ','.join(str(i.id) for i in t.active_items()))" % T_MANUAL)
mt = re.search(r'MT (\S+) ([\d,]+)', info)
MTOK, mids = (mt.group(1), mt.group(2).split(',')) if mt else ('x', [])
st, page = get(mc, '/take/%s' % MTOK)
for k in range(0, len(mids), 10):
    mc.req('/take/%s/page' % MTOK, [('csrf_token', mc.csrf(page)), ('page', str(k // 10 + 1)), ('go', 'next')]
           + [('q_%s' % i, '3') for i in mids[k:k + 10]])
st, page = get(mc, '/take/%s/review' % MTOK)
st, loc, _ = mc.req('/take/%s/submit' % MTOK, {'csrf_token': mc.csrf(page)})
check('F00 the invitation the panel copied (a number typed, no SMS) is answered to the end', st in (302, 303) and mt, '%s %s' % (st, loc))
out = shell("F = env['ts.funnel.event'].sudo(); print('FUN', ' '.join('%s=%d' % (s, F.search_count([('step', '=', s)])) for s in "
            "['start_view', 'start', 'q1', 'finish', 'gate_view', 'gate_signed_in', 'report_view', 'invite_view', 'invite_accept']))")
fm = dict(re.findall(r'(\w+)=(\d+)', out))
check('F01 every funnel step of these flows was counted', len(fm) == 9 and all(int(v) > 0 for v in fm.values()), out.strip()[-200:])
out = shell("F = env['ts.funnel.event'].sudo(); c = lambda d: F.search_count(d); "
            "print('INV', c([('step', '=', 'q1'), ('entry', '=', 'manual')]), c([('step', '=', 'finish'), ('entry', '=', 'manual')]), "
            "c([('step', '=', 'invite_view'), ('entry', '=', 'sms')]), c([('step', '=', 'q1'), ('entry', '=', 'sms')]), "
            "c([('step', '=', 'q1'), ('entry', '=', 'guest')]), "
            "c([('step', 'in', ('q1', 'finish')), ('entry', 'in', ('guest', 'user')), ('instrument_id.ts_guest_ok', '=', False)]))")
check('F03 the invitation path counts welcome viewed, first answer and finished by channel (sms, manual); the guest path its '
      'first answer; self-started attempts of other instruments are never counted',
      re.search(r'INV [1-9]\d* [1-9]\d* [1-9]\d* [1-9]\d* [1-9]\d* 0', out), out.strip()[-80:])
CNT = "F = env['ts.funnel.event'].sudo(); print('CNT', F.search_count([('step', '=', 'start_view')]), F.search_count([('step', '=', 'invite_view')]))"
b = re.search(r'CNT (\d+) (\d+)', shell(CNT)).groups()
bot = {'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'}
raw(client(), '/start', headers=bot)
raw(client(), '/invite/%s' % T_LINK, headers={'User-Agent': 'TelegramBot (like TwitterBot)'})
raw(client(), '/start', headers={'User-Agent': ''})
a_ = re.search(r'CNT (\d+) (\d+)', shell(CNT)).groups()
check('F04 robots and link previews are not counted (no row for a crawler, a messenger preview or an empty agent)', a_ == b,
      '%s %s' % (b, a_))
for _ in range(3):
    raw(client(), '/start')
c_ = re.search(r'CNT (\d+) (\d+)', shell(CNT)).groups()
check('F05 a visit without any cookie writes nothing into a session and is counted at most once per address and minute',
      int(c_[0]) - int(a_[0]) < 3, '%s -> %s' % (a_[0], c_[0]))
e = client(EOT)
check('F02 eot.ir has no /start, no welcome screen and no /i/', e.req('/start')[0] == 404 and e.req('/invite/%s' % T_LINK)[0] == 404
      and e.req('/i/%s' % SHORT)[0] == 404 and e.req('/i/%s/%s' % (SHORT_S, DLV_S))[0] == 404)
shell("env['ts.rate.hit'].sudo().search([]).unlink(); env.cr.commit()")
summary()
