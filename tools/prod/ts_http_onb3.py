#!/usr/bin/env python3
"""onb3 over HTTP against a served CLONE with a LOCAL fake Kavenegar (no SMS or e-mail leaves the machine): the one form
per kind (/panel?kind=… → sign-in → the form with the kind chosen), «شروع کار» on the new dashboard, the welcome SMS, the
member's own try-out («پیش‌نمایش») and its end on the panel's report view with the coach line, the sample report (panel and
public), the one-screen «دعوت تازه» (escalation asked once, the SMS preview, «فرستادن», minors, prepaid refusal), the
permanent link with its QR, the live status stepper, the first-result SMS, «پنل را کامل کنید», the guide-SMS switch, the
colleague join SMS, the help sections, the audience pages (/clinics /hiring /schools /pricing) and the activation funnel.
Risk review fixes: the age question of a counseling panel's permanent link (and the class link's parity), the join-SMS
cap through «ساخت پیوند تازه», at-most-once guide SMS with real commits, and no SMS route on a clone for the flows of
earlier releases (invitation SMS, colleague join SMS) when the clone carries the live Kavenegar address.
eot.ir must stay exactly as it was.
    ts_http_onb3.py DB PORT"""
import http.server, importlib.util, json, os, re, sys, threading, urllib.parse

FAKE_PORT = 18096 + 10 * int(os.environ.get('TS_SLOT', '0'))   # one fake Kavenegar per rehearsal slot (onb2 uses 18097)
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, summary, shell, ensure_user, path_of = lib.Client, lib.check, lib.summary, lib.shell, lib.ensure_user, lib.path_of
TS, EOT = 'talentsearch.ir', 'www.eot.ir'
REQS, MID = [], [930000]


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


def sms_to(phone):
    return [qd.get('message', '') for p_, qd in REQS if p_ == 'sms/send' and phone in qd.get('receptor', '')]


PH = {'cl': '09126654530', 'sc': '09126654531', 'hr': '09126654532', 'pp': '09126654533', 'cand': '09126654534',
      'kid': '09126654535', 'col': '09126654536', 'pcand': '09126654537', 'guard': '09126654538', 'guard2': '09126654539'}
L = {n: 'ts.onb3.%s.http@example.invalid' % n for n in ('cl', 'sc', 'hr', 'pp', 'cand', 'adult', 'minor', 'stu')}
pw = {u: ensure_user(u) for u in L.values()}

out = shell(r"""
L, PH = %r, %r
from odoo import fields
assert env.cr.dbname.startswith('eot_ts')
icp = env['ir.config_parameter'].sudo(); c = env.company.sudo()
print('PREV', icp.get_str('ts_kavenegar.api_base') or '-', int(bool(c.kv_enabled)), int(bool(c.ts_sms_invite)), c.kv_lines or '-',
      icp.get_str('ts_onboard.quiet_start') or '-', icp.get_str('ts_onboard.quiet_end') or '-')
icp.set_str('ts_kavenegar.api_base', 'http://127.0.0.1:%d/v1/%%s/%%s.json')
c.write({'kv_lines': '10004346'})
c.write({'kv_enabled': True, 'kv_api_key': 'FAKEKEY', 'kv_sender': '10004346', 'ts_sms_invite': True})
icp.set_str('ts_onboard.quiet_start', '24'); icp.set_str('ts_onboard.quiet_end', '0')     # never quiet during this run
icp.set_str('ts_onboard.nudges_enabled', '1'); icp.set_str('ts_panel.invites_per_hour', '200')
U = env['res.users'].with_context(active_test=False)
for ph in PH.values():
    for u in U.search([('login', '=', ph)]):
        u.sudo().write({'active': False, 'login': 'old.onb3.%%d' %% u.id})
env['res.partner'].with_context(active_test=False).search([('ts_phone', 'in', list(PH.values()))]).write({'ts_phone': False})
M = env['ts.workspace.member'].sudo().with_context(active_test=False)
for n in ('cl', 'sc', 'hr', 'pp', 'cand'):
    u = env['res.users'].search([('login', '=', L[n])])
    u.partner_id.write({'ts_phone': PH[n], 'ts_phone_verified_at': fields.Datetime.now()})
    if n == 'cl':
        u.write({'name': 'مالک مرکز آزمون onb3'})
    # earlier runs on this clone: their panels are closed and out of the three-a-day limit
    old = M.search([('user_id', '=', u.id), ('role', '=', 'owner')])
    old.workspace_id.filtered(lambda w: w.state == 'active').write({'state': 'closed'})
    if old:
        env.cr.execute("UPDATE ts_workspace_member SET create_date = now() - interval '3 days' WHERE id IN %%s", [tuple(old.ids)])
env['ts.rate.hit'].sudo().search([]).unlink()
F = env['ts.funnel.event'].sudo()
print('FUN', *[F.search_count([('step', '=', s), ('panel_kind', '=', k)]) for s, k in (
    ('panel_created', 'clinic'), ('panel_created', 'school'), ('panel_created', 'hr'), ('self_test_done', 'clinic'),
    ('first_invite', 'clinic'), ('first_result_opened', 'clinic'))])
env.cr.commit()
""" % (L, PH, FAKE_PORT))
m = re.search(r'PREV (\S+) (\d) (\d) (\S+) (\S+) (\S+)', out)
assert m, out[-2500:]
PREV = m.groups()
fm = re.search(r'FUN (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)', out)
FUN0 = [int(x) for x in fm.groups()]


def login(n):
    c = Client(TS)
    assert c.login(L[n], pw[L[n]]), n
    return c


def get(c, path):
    """GET that follows up to three redirects."""
    for _ in range(4):
        st, loc, body = c.req(path)
        if st in (301, 302, 303) and loc:
            path = path_of(loc)
            continue
        break
    return st, body


def post(c, path, data, page=None):
    pairs = list(data.items())
    pairs.append(('csrf_token', c.csrf(page if page is not None else c.req('/my')[2] or c.req('/web/login')[2])))
    return c.req(path, pairs)


def section(body, sid):
    mm = re.search(r'<section[^>]*id="%s".*?</section>' % sid, body, re.S)
    return mm.group(0) if mm else ''


def make_panel(c, kind, name):
    st, form = get(c, '/my/workspaces/new?kind=' + kind)
    st2, loc, body = post(c, '/my/workspaces/new/create', {'kind': kind, 'name': name, 'own_name': '', 'accept': '1'}, form)
    mm = re.search(r'/my/workspaces/(\d+)', loc or '')
    return (mm.group(1) if mm else None), st, form, st2, loc


def fa(n):
    return str(n).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))


# ================================================================ A. the one form, per kind
anon = Client(TS)
st, loc, _ = anon.req('/panel?kind=clinic')
check('A01 «ساخت پنل رایگان» of an audience page lands in the one form with the kind chosen (/panel?kind=… → /my/workspaces/new?kind=…)',
      st in (302, 303) and loc.endswith('/my/workspaces/new?kind=clinic'), '%s %s' % (st, loc))
st, loc, _ = anon.req('/my/workspaces/new?kind=clinic')
check('A02 ...signed out: to the sign-in first, back to the form after it', st in (302, 303)
      and 'kind=clinic' in urllib.parse.unquote(urllib.parse.unquote(loc)), loc)
st, body = get(anon, '/panel')
check('A03 /panel lists the four kinds (each card opens the form with its kind)', st == 200 and all(
    ('/my/workspaces/new?kind=%s' % k) in body for k in ('clinic', 'solo', 'school', 'org'))
      and 'مشاور یا روان‌شناس مستقل' in body and 'استخدام و منابع انسانی' in body, str(st))
cl = login('cl')
st, form = get(cl, '/my/workspaces/new?kind=clinic')
check('A04 the one form: the kind chosen, panel name, «نام شما» filled with the account name; no licence, no escalation, no terms box',
      st == 200 and re.search(r'value="clinic"[^>]*checked', form) and 'name="own_name"' in form and 'مالک مرکز آزمون onb3' in form
      and 'name="license_number"' not in form and 'escalation_ok' not in form and 'name="terms"' not in form
      and 'name="accept"' in form and 'با ساخت پنل، <a href="/panel/terms">شرایط استفاده</a> را می‌پذیرید' in form, str(st))
WC, st, form, st2, loc = make_panel(cl, 'clinic', 'مرکز مشاورهٔ آزمون onb3')
check('A05 «ساخت پنل» makes the counseling-center panel at once (no licence, no escalation asked)', WC and st2 in (302, 303), '%s %s' % (st2, loc))
W = '/my/workspaces/%s' % WC
info = shell("w = env['ts.workspace'].browse(%s); r = env['ts.onb.nudge'].search([('workspace_id', '=', w.id), ('kind', '=', 'welcome')]); "
             "print('W', w.ts_kind, w.purpose, bool(w.escalation_contact_id), w.state, r.state)" % WC)
check('A06 kind «clinic», purpose clinical, active, no escalation contact yet', 'W clinic clinical False active' in info, info[-120:])
welcome = sms_to(PH['cl'])
check('A07 the welcome SMS: «پنل … ساخته شد. نخستین قدم: خودتان امتحان کنید.» with the dashboard link, nothing else named',
      welcome and 'ساخته شد. نخستین قدم: خودتان امتحان کنید.' in welcome[-1] and ('/my/workspaces/%s' % WC) in welcome[-1]
      and 'sent' in info, str(welcome[-1:])[:200])

# ================================================================ B. «شروع کار» on the first dashboard
st, dash = get(cl, W)
start = section(dash, 'tso-start')
check('B01 «شروع کار»: ۱ از ۴, «پنل ساخته شد» done, the current step «خودتان امتحان کنید», help per kind, «بعداً»',
      st == 200 and 'شروع کار' in start and '۱ از ۴' in start and 'پنل ساخته شد' in start and 'خودتان امتحان کنید' in start
      and 'نخستین دعوت' in start and 'نخستین نتیجه' in start and 'href="/help/panel#start-clinic"' in start and 'بعداً' in start, str(st))
check('B02 the hero: «اول خودتان ببینید مراجع چه می‌بیند», one primary button «امتحان کنید» (POST /try), «یا نمونهٔ گزارش را ببینید»',
      'اول خودتان ببینید مراجع چه می‌بیند' in start and ('action="%s/try"' % W) in start and 'امتحان کنید' in start
      and ('href="%s/sample"' % W) in start and 'یا نمونهٔ گزارش را ببینید' in start)
prim = [a for a in re.findall(r'<(?:a|button)[^>]*class="[^"]*ts-btn--primary[^"]*"[^>]*>', dash)]
check('B03 one primary action on the page (the header «دعوت تازه» is not primary while the card leads)', len(prim) == 1, str(len(prim)))
check('B04 the usage line «تا امروز ۰ نتیجه؛ در دورهٔ آزمایشی رایگان»', 'تا امروز ۰ نتیجه؛ در دورهٔ آزمایشی رایگان' in dash)
check('B05 the old lists are gone', 'گام‌های راه‌اندازی' not in dash and 'راه‌اندازی مرکز' not in dash)

# ================================================================ S. the sample report inside the panel
st, smp = get(cl, W + '/sample')
check('S01 «نمونهٔ گزارش»: the real counselor report template, labelled «نمونه — داده‌های ساختگی», a synthetic person',
      st == 200 and 'نمونه — داده‌های ساختگی' in smp and 'مریم نمونه' in smp, str(st))
check('S02 ...and one next step «اول خودتان امتحان کنید»', 'اول خودتان امتحان کنید' in smp)

# ================================================================ T. the try-out
st, loc, _ = post(cl, W + '/try', {}, dash)
check('T01 «امتحان کنید» starts the try-out and opens its first part', st in (302, 303) and '/take/' in loc, '%s %s' % (st, loc))
fin = shell(r"""
w = env['ts.workspace'].browse(%s)
a = env['ts.assignment'].sudo().search([('workspace_id', '=', w.id), ('ts_preview', '=', True)], limit=1)
print('PV', a.channel, a.client_id.source, a.battery_id.code, a.invitee_name[:11])
for _ in range(12):
    a.invalidate_recordset()
    left = a.ts_battery_attempts().filtered(lambda t: t.state != 'done')
    if not left:
        break
    t = left[0].sudo()
    if t.state == 'consent':
        t.give_consent(research=False, role='self')
    for it in t.active_items():
        t.save_answer(it.id, 1 + it.id %% 4)
    t.action_submit()
a.invalidate_recordset()
print('DONE', a.state, env['ts.usage.event'].sudo().search_count([('attempt_id', 'in', a.ts_battery_attempts().ids)]))
env.cr.commit()
""" % WC)
check('T02 a «پیش‌نمایش» invitation of BAT-INTAKE-1 on a preview client', 'PV preview preview BAT-INTAKE-1 پیش‌نمایش' in fin, fin[-160:])
check('T03 finished, and never counted as usage', 'DONE done 0' in fin, fin[-80:])
st, loc, _ = cl.req(W + '/try/end')
check('T04 the end of the try-out lands on the panel\'s report view (?preview=1)', st in (302, 303) and '?preview=1' in loc
      and '/clients/' in loc, loc)
st, rep = get(cl, path_of(loc))
coach = section(rep, 'tso-coach')
check('T05 the real staff report with the coach line «گزارش مراجعانتان همین‌جا می‌آید» and under it «حالا نخستین مراجع را دعوت کنید»',
      st == 200 and 'گزارش مراجعانتان همین‌جا می‌آید' in coach and 'حالا نخستین مراجع را دعوت کنید' in coach
      and ('href="%s/invites/new"' % W) in coach and 'پیش‌نمایش' in coach, str(st))
st, dash = get(cl, W)
start = section(dash, 'tso-start')
check('T06 «شروع کار» ۲ از ۴: the next step is the first invitation', '۲ از ۴' in start and ('href="%s/invites/new"' % W) in start
      and 'حالا نخستین مراجع را دعوت کنید' in start)
st, inv_list = get(cl, W + '/invites')
check('T07 the try-out is in no list of the panel (invitations)', 'پیش‌نمایش —' not in inv_list)
st, cli = get(cl, W + '/clients')
check('T08 ...nor clients', 'پیش‌نمایش —' not in cli)

# ================================================================ I. one-screen «دعوت تازه»
st, one = get(cl, W + '/invites/new')
check('I01 «دعوت تازه» is one screen: two equal choices, name and mobile, the starter preselected, the SMS shown, «فرستادن»',
      st == 200 and 'فرستادن به یک نفر' in one and 'پیوند همیشگی و QR' in one and 'name="new_name"' in one and 'name="new_phone"' in one
      and 'ارزیابی آغاز مشاوره' in one and 'متن پیامک' in one and 'id="tso-pick"' in one and 'تنظیمات بیشتر' in one and 'id="tso-send"' in one, str(st))
check('I02 the escalation question is asked here, once (a counseling center without its contact)', 'name="escalation_ok"' in one
      and 'پیگیری فوری نشانه‌های خطر در این مرکز با من است' in one)
check('I03 the step wizard is still reachable for a registered participant (?wizard=1)', 'wizard=1' in one)
st, b, page = post(cl, W + '/invites/new', {'one': '1', 'attest': '1', 'new_name': 'مراجع آزمون onb3', 'new_phone': PH['cand']}, one)
check('I04 «فرستادن» without the escalation tick is refused with the question', st == 200 and 'پیگیری فوری' in page, str(st))
n_sms = len(sms_to(PH['cand']))
st, loc, _ = post(cl, W + '/invites/new', {'one': '1', 'attest': '1', 'escalation_ok': '1', 'new_name': 'مراجع آزمون onb3',
                                           'new_phone': PH['cand']}, one)
check('I05 with the tick: the invitation is made and its page opens (?new=1)', st in (302, 303) and re.search(r'/invites/\d+\?new=1', loc or ''),
      '%s %s' % (st, loc))
AID = re.search(r'/invites/(\d+)', loc or '/invites/0').group(1)
check('I06 the invitation SMS went to the person', len(sms_to(PH['cand'])) == n_sms + 1)
info = shell("a = env['ts.assignment'].browse(%s); print('A', a.battery_id.code, a.sms_consent, bool(a.workspace_id.escalation_contact_id), a.channel)" % AID)
check('I07 the starter battery, SMS consent attested by «فرستادن», the escalation contact set once', 'A BAT-INTAKE-1 True True' in info, info[-80:])
st, one2 = get(cl, W + '/invites/new')
check('I08 the next «دعوت تازه» no longer asks the escalation question', 'name="escalation_ok"' not in one2)
st, inv_list = get(cl, W + '/invites')
check('I09 the live status stepper «فرستاده شد → باز شد → در حال پاسخ → آماده» in the invitation list', 'tsp-steps' in inv_list
      and 'فرستاده شد' in inv_list and 'در حال پاسخ' in inv_list and 'آماده' in inv_list)
st, dash = get(cl, W)
check('I10 the dashboard: «۳ از ۴», waiting for the first result, and «دعوت‌های اخیر» with the stepper', '۳ از ۴' in section(dash, 'tso-start')
      and 'منتظر نخستین نتیجه' in dash and 'tsp-steps' in section(dash, 'tso-recent'))

# ================================================================ L. the permanent link
st, b, page = post(cl, W + '/invites/new', {'one': 'link'}, one2)
check('L01 «ساخت پیوند همیشگی» makes the panel\'s permanent link', st in (302, 303) and 'mode=link' in (b or ''), '%s %s' % (st, b))
st, lk = get(cl, W + '/invites/new?mode=link')
url = re.search(r'id="tso_link_url"[^>]*value="([^"]+)"', lk) or re.search(r'value="([^"]+/c/[^"]+)"[^>]*id="tso_link_url"', lk)
check('L02 the link pane: the /c/ link, copy and share, «دریافت QR», the QR image', url and '/c/' in url.group(1)
      and ('src="%s/link/qr.png"' % W) in lk and 'دریافت QR' in lk and re.search(r'value="link"[^>]*checked', lk), str(st))
from urllib.request import Request
r = Request(lib.BASE + W + '/link/qr.png?download=1', headers={'Host': TS, 'X-Forwarded-Proto': 'https'})
try:
    resp = cl.op.open(r, timeout=60)
    st, ctype, disp, data = resp.status, resp.headers.get('Content-Type', ''), resp.headers.get('Content-Disposition', ''), resp.read()
except Exception as e:      # noqa: BLE001
    st, ctype, disp, data = getattr(e, 'code', 0), '', '', b''
check('L03 the QR downloads as a PNG file', st == 200 and ctype.startswith('image/png') and 'attachment' in disp and data[:4] == b'\x89PNG',
      '%s %s %s' % (st, ctype, disp))
if url:
    st, joinp = get(Client(TS), path_of(url.group(1)))
    check('L04 the permanent link opens the join page for anyone (sign-in with the person\'s own number)', st == 200 and 'ارزیابی آغاز مشاوره' in joinp,
          str(st))
check('L05 eot.ir never serves the QR (sign-in redirect or 404, never the image)', Client(EOT).req(W + '/link/qr.png')[0] in (302, 303, 404))

# ================================================================ Y. the age question on a counseling panel's permanent link
TOK = re.search(r'/c/([^"/?#]+)', url.group(1)).group(1) if url else 'none'
ad, mi = login('adult'), login('minor')
st, jp = get(ad, '/c/' + TOK)
age_q = re.search(r'<fieldset[^>]*id="tso-age-q".*?</fieldset>', jp, re.S)
check('Y01 signed in, the join form of a counseling panel asks «۱۸ سال یا بیشتر دارم» / «کمتر از ۱۸ سال دارم» (a required choice)',
      st == 200 and age_q and '۱۸ سال یا بیشتر دارم' in age_q.group(0) and 'کمتر از ۱۸ سال دارم' in age_q.group(0)
      and 'required' in age_q.group(0), str(st))
st, mp_ = get(mi, '/c/' + TOK)
st, loc, _ = post(mi, '/c/%s/join' % TOK, {'name': 'نوجوان آزمون onb3', 'share': '1', 'age': 'minor'}, mp_)
st2, page = get(mi, '/c/' + TOK)
nm = shell("print('NM', env['ts.panel.client'].sudo().search_count([('workspace_id', '=', %s), ('user_id.login', '=', %r)]), "
           "env['ts.audit.event'].sudo().search_count([('event_type', '=', 'campaign.join_minor'), ('workspace_id', '=', %s)]))"
           % (WC, L['minor'], WC))
check('Y02 «کمتر از ۱۸ سال دارم» is refused kindly on the same page («برای زیر ۱۸ سال، مرکز باید دعوت جداگانه با رضایت ولی بفرستد.»); '
      'no client or invitation is made; the answer is recorded', st in (302, 303) and (loc or '').endswith('/c/' + TOK)
      and 'برای زیر ۱۸ سال، مرکز باید دعوت جداگانه با رضایت ولی بفرستد.' in page and 'NM 0 1' in nm, nm[-40:])
st, loc, _ = post(ad, '/c/%s/join' % TOK, {'name': 'بزرگسال آزمون onb3', 'share': '1'}, jp)
st2, jp2 = get(ad, '/c/' + TOK)
check('Y03 without an answer nobody joins; the page asks again', st in (302, 303) and 'لطفاً بگویید ۱۸ سال یا بیشتر دارید یا کمتر.' in jp2)
st, loc, _ = post(ad, '/c/%s/join' % TOK, {'name': 'بزرگسال آزمون onb3', 'share': '1', 'age': 'adult'}, jp2)
ag = shell("c = env['ts.panel.client'].sudo().search([('workspace_id', '=', %s), ('user_id.login', '=', %r)]); "
           "print('AG', c.age_group, c.source, env['ts.audit.event'].sudo().search_count([('event_type', '=', 'campaign.join_age'), "
           "('workspace_id', '=', %s)]))" % (WC, L['adult'], WC))
check('Y04 «۱۸ سال یا بیشتر دارم» joins and goes on to consent; the client is an adult, the answer recorded',
      st in (302, 303) and '/take/' in (loc or '') and 'AG adult open_link 1' in ag, '%s %s' % (loc, ag[-40:]))

# ================================================================ R. the first result: SMS to the owner, «پنل را کامل کنید»
n_owner = len(sms_to(PH['cl']))
fin = shell(r"""
a = env['ts.assignment'].sudo().browse(%s)
u = env['res.users'].search([('login', '=', %r)])
a.action_accept(u, share=True)
for _ in range(12):
    a.invalidate_recordset()
    left = a.ts_battery_attempts().filtered(lambda t: t.state != 'done')
    if not left:
        break
    t = left[0].sudo()
    if t.state == 'consent':
        t.give_consent(research=False, role='self')
    for it in t.active_items():
        t.save_answer(it.id, 1 + it.id %% 4)
    t.action_submit()
a.invalidate_recordset()
print('R', a.state, bool(a.workspace_id.ts_onb_result_ready_at), a.client_id.id, a.id)
env.cr.commit()
""" % (AID, L['cand']))
rm = re.search(r'R (\w+) (\w+) (\d+) (\d+)', fin)
check('R01 the client finished and shared: the first result is ready', rm and rm.group(1) == 'done' and rm.group(2) == 'True', fin[-120:])
first = sms_to(PH['cl'])[n_owner:]
check('R02 the owner gets «نخستین نتیجه در پنل … آماده است» with the link, no test or client named', first
      and 'نخستین نتیجه در پنل' in first[-1] and 'آماده است' in first[-1] and 'مراجع آزمون' not in first[-1]
      and 'ارزیابی آغاز' not in first[-1], str(first[-1:])[:200])
st, dash = get(cl, W)
check('R03 «شروع کار»: «نخستین نتیجه آماده است» with «دیدن نتیجه»', 'نخستین نتیجه آماده است' in dash and 'دیدن نتیجه' in dash)
if rm:
    st, rp = get(cl, W + '/clients/%s/b/%s' % (rm.group(3), rm.group(4)))
    check('R04 the owner opens the result (the counselor report)', st == 200, str(st))
st, dash = get(cl, W)
more = section(dash, 'tso-more')
check('R05 the first real result opened: «شروع کار» is gone, «پنل را کامل کنید» appears with a celebration line',
      'id="tso-start"' not in dash and 'پنل را کامل کنید' in more and 'نخستین نتیجه را دیدید' in more
      and 'نام و لوگو روی گزارش' in more and 'دعوت همکاران' in more, str(st))
check('R06 the second card has no licence item for a center owner who does not counsel', 'رسیدگی به پروانه' not in more)

# ================================================================ G. guide SMS switch, colleague join SMS, «بعداً»
mid = shell("print('MID', env['ts.workspace.member'].search([('workspace_id', '=', %s), ('role', '=', 'owner')], limit=1).id)" % WC)
MIDO = re.search(r'MID (\d+)', mid).group(1)
st, mp = get(cl, W + '/members/' + MIDO)
check('G01 the member\'s own page has «پیامک‌های راهنما» (on)', st == 200 and 'id="tso-guide"' in mp and 'روشن' in section(mp, 'tso-guide'), str(st))
st, loc, _ = post(cl, W + '/members/%s/guide-sms' % MIDO, {'on': '0'}, mp)
st2, mp2 = get(cl, W + '/members/' + MIDO)
check('G02 switched off by the member himself', st in (302, 303) and 'خاموش' in section(mp2, 'tso-guide'))
post(cl, W + '/members/%s/guide-sms' % MIDO, {'on': '1'}, mp2)
st, mem = get(cl, W + '/members')
n_col = len(sms_to(PH['col']))
st, loc, _ = post(cl, W + '/members/invite', {'role': 'clinician', 'phone': PH['col']}, mem)
st2, mem2 = get(cl, path_of(loc)) if loc else (0, '')
check('G03 a colleague invited with a mobile number gets the join SMS (/j/ link) and the page says so',
      len(sms_to(PH['col'])) == n_col + 1 and '/j/' in sms_to(PH['col'])[-1] and 'پیامک دعوت برای همکار فرستاده شد' in mem2,
      str(sms_to(PH['col'])[-1:])[:160])
check('G04 the members form says «فرستادن دعوت»', 'فرستادن دعوت' in mem)
mv = re.search(r'minv=(\d+)', loc or '')
st, loc, _ = post(cl, W + '/members/invites/%s/resend' % (mv.group(1) if mv else 0), {}, mem2)
mv2 = re.search(r'minv=(\d+)', loc or '')
st, mem3 = get(cl, path_of(loc)) if loc else (0, '')
st, loc, _ = post(cl, W + '/members/invites/%s/resend' % (mv2.group(1) if mv2 else 0), {}, mem3)
st, mem4 = get(cl, path_of(loc)) if loc else (0, '')
check('G04b «ساخت پیوند تازه» twice: the second resend would be the third join SMS to that number today; it is held back and the '
      'page says «سقف پیامک دعوت امروز پر شده؛ پیوند را خودتان بفرستید.» (the new link is still shown)',
      len(sms_to(PH['col'])) == n_col + 2 and 'سقف پیامک دعوت امروز پر شده؛ پیوند را خودتان بفرستید.' in mem4 and 'id="tsp-newinv"' in mem4,
      str(len(sms_to(PH['col'])) - n_col))
st, loc, _ = post(cl, W + '/more/hide', {}, dash)
check('G05 «بعداً» hides «پنل را کامل کنید» for this member', st in (302, 303) and 'id="tso-more"' not in get(cl, W)[1])
first_cl = lambda: [b_ for b_ in sms_to(PH['cl']) if 'نخستین نتیجه' in b_]
n_first = len(first_cl())
dup = shell(r"""
from unittest.mock import patch
N = env['ts.onb.nudge'].sudo()
ws = env['ts.workspace'].browse(%s)
m = ws.member_ids.filtered(lambda x: x.role == 'owner')[:1]
row, _n = N._new(ws, m, 'first_result', key='first_result:dup-http')
env.cr.commit()
with patch.object(type(N), '_ts_mark', lambda self, ok: (_ for _ in ()).throw(RuntimeError('rolled back after the gateway'))):
    N.browse(row.id)._ts_send(commit=True)
env.invalidate_all()
s1 = N.browse(row.id).state
N._cron_onb_nudges()
N.browse(row.id)._ts_send(commit=True)
env.invalidate_all()
print('DUP', s1, N.browse(row.id).state)
env.cr.commit()
""" % WC)
check('G06 at most once with real commits: the gateway took the SMS, its result write rolled back; the row stays «sending» and '
      'neither the hourly run nor a second send repeats it', 'DUP sending sending' in dup and len(first_cl()) == n_first + 1,
      '%s %s' % (dup[-60:], len(first_cl()) - n_first))

# ================================================================ K. school: minors on one screen, the class link
sc = login('sc')
WS_, st, form, st2, loc = make_panel(sc, 'school', 'مدرسهٔ آزمون onb3')
check('K01 a school panel from the one form', WS_ and st2 in (302, 303), loc)
SW = '/my/workspaces/%s' % WS_
st, dash = get(sc, SW)
start = section(dash, 'tso-start')
check('K02 «شروع کار» for a school: «اول خودتان ببینید دانش‌آموز چه می‌بیند», «پیوند کلاس», «نخستین گزارش کلاس»',
      'اول خودتان ببینید دانش‌آموز چه می‌بیند' in start and 'پیوند کلاس' in start and 'نخستین گزارش کلاس' in start
      and 'href="/help/panel#start-school"' in start)
st, smp = get(sc, SW + '/sample')
check('K03 the school sample: the real talent report, labelled «نمونه — داده‌های ساختگی»', st == 200 and 'نمونه — داده‌های ساختگی' in smp
      and 'آرمان نمونه' in smp, str(st))
st, one = get(sc, SW + '/invites/new?mode=link')
check('K04 a school opens «دعوت تازه» on the permanent link', st == 200 and bool(re.search(r'value="link"[^>]*checked', one)), str(st))
st, b, page = post(sc, SW + '/invites/new', {'one': '1', 'attest': '1', 'new_name': 'دانش‌آموز آزمون onb3', 'new_phone': PH['kid'],
                                             'new_age': 'minor'}, one)
check('K05 a minor without the guardian attestation is refused with the reason', st == 200 and 'رضایت ولی' in page, str(st))
st, loc, _ = post(sc, SW + '/invites/new', {'one': '1', 'attest': '1', 'new_name': 'دانش‌آموز آزمون onb3', 'new_phone': PH['kid'],
                                            'new_age': 'minor', 'guardian_ok': '1'}, one)
check('K06 ...with it, the invitation is made', st in (302, 303) and '?new=1' in (loc or ''), '%s %s' % (st, loc))
st, b, page = post(sc, SW + '/invites/new', {'one': 'link'}, one)
st, lks = get(sc, SW + '/invites/new?mode=link')
surl = re.search(r'id="tso_link_url"[^>]*value="([^"]+)"', lks) or re.search(r'value="([^"]+/c/[^"]+)"[^>]*id="tso_link_url"', lks)
STOK = re.search(r'/c/([^"/?#]+)', surl.group(1)).group(1) if surl else 'none'
stu = login('stu')
st, sjp = get(stu, '/c/' + STOK)
st, loc, _ = post(stu, '/c/%s/join' % STOK, {'name': 'دانش‌آموز پیوند آزمون', 'share': '1'}, sjp)
sg = shell("c = env['ts.panel.client'].sudo().search([('workspace_id', '=', %s), ('user_id.login', '=', %r)]); print('SG', c.age_group)"
           % (WS_, L['stu']))
check('K07 the class link keeps its pre-onb3 behaviour: no age question, the student joins straight to consent, the client '
      'as before («unknown»: the consent screen asks the assent)', 'id="tso-age-q"' not in sjp and 'name="name"' in sjp
      and st in (302, 303) and '/take/' in (loc or '') and 'SG unknown' in sg, '%s %s' % (loc, sg[-30:]))

# ================================================================ H. hiring: the sample position, the HR admin as first candidate
hr = login('hr')
WH, st, form, st2, loc = make_panel(hr, 'org', 'شرکت آزمون onb3')
HW = '/my/workspaces/%s' % WH
st, pos = get(hr, HW + '/positions')
check('H01 an employment panel starts with «کارشناس فروش (نمونه)» marked «نمونه»', st == 200 and 'کارشناس فروش (نمونه)' in pos
      and 'tsh-sample' in pos, str(st))
st, dash = get(hr, HW)
start = section(dash, 'tso-start')
check('H02 «شروع کار» for hiring: «اول خودتان ببینید داوطلب چه می‌بیند», «دعوت داوطلب‌ها»', 'اول خودتان ببینید داوطلب چه می‌بیند' in start
      and 'دعوت داوطلب‌ها' in start and 'href="/help/panel#start-hr"' in start)
st, loc, _ = post(hr, HW + '/try', {}, dash)
check('H03 the try-out of hiring starts (BAT-HR-SHORT)', st in (302, 303) and '/take/' in loc, loc)
pid = re.search(r'/positions/(\d+)', pos)
if pid:
    st, pp_ = get(hr, HW + '/positions/' + pid.group(1))
    check('H04 the position page lists the HR admin as «پیش‌نمایش» candidate, the counts leave it out', st == 200
          and 'پیش‌نمایش —' in pp_ and 'tsh-sample-note' in pp_, str(st))
st, one = get(hr, HW + '/invites/new')
check('H05 «دعوت تازه» of a hiring panel points to the positions and has no permanent-link choice', st == 200
      and 'موقعیت‌های شغلی' in one and 'id="tso-seg"' not in one, str(st))
st, smp = get(hr, HW + '/sample')
check('H06 the hiring sample: the real job-fit block for «کارشناس فروش», labelled', st == 200 and 'نمونه — داده‌های ساختگی' in smp
      and 'کارشناس فروش' in smp, str(st))

# ================================================================ P. prepaid: the try-out is free, an invitation without credit is refused
pp = login('pp')
WP, st, form, st2, loc = make_panel(pp, 'clinic', 'مرکز پیش‌پرداخت آزمون onb3')
PW = '/my/workspaces/%s' % WP
pr0 = shell("b = env['ts.battery'].sudo().search([('code', '=', 'BAT-INTAKE-1')]); print('PRICE', int(b.ts_list_price or 0)); "
            "w = env['ts.workspace'].browse(%s); w.billing_mode = 'prepaid'; b.write({'ts_list_price': 3000000}); env.cr.commit()" % WP)
PRICE0 = (re.search(r'PRICE (\d+)', pr0) or re.search(r'(0)', '0')).group(1)
st, dash = get(pp, PW)
st, loc, _ = post(pp, PW + '/try', {}, dash)
check('P01 a prepaid panel with no credit can still try (a try-out is never billed)', st in (302, 303) and '/take/' in loc, loc)
st, one = get(pp, PW + '/invites/new')
st, b, page = post(pp, PW + '/invites/new', {'one': '1', 'attest': '1', 'escalation_ok': '1', 'new_name': 'مراجع پیش‌پرداخت onb3',
                                             'new_phone': PH['pcand']}, one)
cnt = shell("print('C', env['ts.assignment'].search_count([('workspace_id', '=', %s), ('ts_preview', '=', False)]), "
            "env['ts.wallet.txn'].search_count([('workspace_id', '=', %s), ('type', '=', 'hold')]))" % (WP, WP))
check('P02 an invitation without credit is refused with the credit message; nothing made, nothing held', st == 200
      and 'اعتبار پنل برای این دعوت کافی نیست' in page and 'C 0 0' in cnt, '%s %s' % (st, cnt[-40:]))

# ================================================================ W. help, audience pages, public samples, isolation
st, hp = get(anon, '/help/panel')
gs = re.search(r'<article[^>]*id="getting-started".*?</article>', hp, re.S)
gs = gs.group(0) if gs else ''
counts = [len(re.findall(r'<li>', (re.search(r'id="%s".*?</ol>' % k, gs, re.S) or re.search('x', 'x')).group(0))) for k in
          ('start-clinic', 'start-solo', 'start-school', 'start-hr')]
check('W01 /help/panel#getting-started: «شروع کار» per kind, five items each, listed first in the contents', st == 200 and counts == [5, 5, 5, 5]
      and hp.index('href="#getting-started"') < hp.index('href="#invite"'), str(counts))
check('W02 the help has «استخدام و موقعیت‌های شغلی» and «پنل را کامل کنید»', 'id="hr"' in hp and 'id="more"' in hp)
for path, kind, sample in (('/clinics', 'clinic', 'clinic'), ('/hiring', 'org', 'hr'), ('/schools', 'school', 'school')):
    st, pg = get(anon, path)
    t = re.search(r'<title>(.*?)</title>', pg, re.S)
    check('W03 %s: one h1, «ساخت پنل رایگان» to the one form, «نمونهٔ گزارش», questions, a Persian title; no pilot or contact form' % path,
          st == 200 and pg.count('<h1') == 1 and ('href="/panel?kind=%s"' % kind) in pg and ('href="/sample/%s"' % sample) in pg
          and 'نمونهٔ گزارش' in pg and pg.count('ts-faq__item') >= 3 and t and 'استعدادیاب' in t.group(1)
          and 'پایلوت' not in pg and 'contact?topic=partner' not in pg and 'دورهٔ آزمایشی' in pg,
          '%s %s' % (st, t.group(1).strip()[:60] if t else '-'))
st, pr = get(anon, '/pricing')
check('W04 /pricing: every kind free in early access, links to the audience pages', st == 200 and 'در دورهٔ آزمایشی، همهٔ پنل‌ها رایگان‌اند' in pr
      and 'href="/clinics"' in pr and 'href="/hiring"' in pr and 'href="/schools"' in pr, str(st))
for k in ('clinic', 'solo', 'school', 'hr'):
    st, sp_ = get(anon, '/sample/' + k)
    check('W05 /sample/%s: the public sample, labelled, with «ساخت پنل رایگان»' % k, st == 200 and 'نمونه — داده‌های ساختگی' in sp_
          and 'ساخت پنل رایگان' in sp_, str(st))
check('W06 an unknown sample kind is 404', anon.req('/sample/x')[0] == 404)
st, home = get(anon, '/')
check('W07 the home hero links go to the audience pages', 'href="/clinics"' in home and 'href="/hiring"' in home and 'href="/schools"' in home)
st, loc, _ = anon.req('/employers')
check('W08 /employers → /hiring (301)', st == 301 and loc.endswith('/hiring'), '%s %s' % (st, loc))
e = Client(EOT)
check('W09 eot.ir serves none of it', all(e.req(p)[0] == 404 for p in ('/clinics', '/hiring', '/sample/clinic')))

# ================================================================ X. a clone that carries the live Kavenegar address sends nothing
x = shell(r"""
icp = env['ir.config_parameter'].sudo()
icp.set_str('ts_kavenegar.api_base', 'https://api.kavenegar.com/v1/%s/%s.json')
env.company.sudo().write({'kv_enabled': True, 'kv_api_key': 'FAKEKEY', 'ts_sms_invite': True})
env.cr.commit()
print('LIVEBASE ok')
""")
n_all = len(REQS)
st, one = get(cl, W + '/invites/new')
st, loc, _ = post(cl, W + '/invites/new', {'one': '1', 'attest': '1', 'new_name': 'مراجع نگهبان onb3', 'new_phone': PH['guard']}, one)
gid = re.search(r'/invites/(\d+)', loc or '/invites/0').group(1)
st, mem = get(cl, W + '/members')
st, loc2, _ = post(cl, W + '/members/invite', {'role': 'clinician', 'phone': PH['guard2']}, mem)
xg = shell("a = env['ts.assignment'].sudo().browse(%s); i = env['ts.member.invite'].sudo().search([('phone', '=', %r)], limit=1); "
           "print('XG', bool(a.sms_sent_at), bool(i.sms_sent), env['kavenegar.message'].sudo().search_count([('receptor', 'in', (%r, %r))]))"
           % (gid, PH['guard2'], PH['guard'], PH['guard2']))
check('X01 with the live Kavenegar address on a clone, the invitation SMS and the colleague join SMS of earlier flows reach no '
      'gateway at all (not even the local fake): nothing marked sent, nothing logged', 'LIVEBASE ok' in x and len(REQS) == n_all
      and 'XG False False 0' in xg, '%s %s' % (len(REQS) - n_all, xg[-40:]))
shell("env['ir.config_parameter'].sudo().set_str('ts_kavenegar.api_base', 'http://127.0.0.1:%d/v1/%%s/%%s.json'); env.cr.commit()" % FAKE_PORT)

# ================================================================ F. the activation funnel (no personal data)
fo = shell(r"""
F = env['ts.funnel.event'].sudo()
print('FUN', *[F.search_count([('step', '=', s), ('panel_kind', '=', k)]) for s, k in (
    ('panel_created', 'clinic'), ('panel_created', 'school'), ('panel_created', 'hr'), ('self_test_done', 'clinic'),
    ('first_invite', 'clinic'), ('first_result_opened', 'clinic'))])
""")
fm = re.search(r'FUN (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)', fo)
FUN1 = [int(x) for x in fm.groups()] if fm else [0] * 6
check('F01 activation events by kind: panel_created (clinic ×2, school, hr), self_test_done, first_invite, first_result_opened',
      FUN1[0] - FUN0[0] == 2 and FUN1[1] - FUN0[1] == 1 and FUN1[2] - FUN0[2] == 1 and FUN1[3] - FUN0[3] == 1
      and FUN1[4] - FUN0[4] == 1 and FUN1[5] - FUN0[5] == 1, str([b_ - a_ for a_, b_ in zip(FUN0, FUN1)]))

srv.shutdown()
shell("""
c = env.company.sudo(); icp = env['ir.config_parameter'].sudo()
icp.set_str('ts_kavenegar.api_base', '%s' if '%s' != '-' else '')
c.write({'kv_enabled': bool(%s), 'ts_sms_invite': bool(%s)})
icp.set_str('ts_onboard.quiet_start', '%s' if '%s' != '-' else '')
icp.set_str('ts_onboard.quiet_end', '%s' if '%s' != '-' else '')
env['ts.battery'].sudo().search([('code', '=', 'BAT-INTAKE-1')]).write({'ts_list_price': %s})
env.cr.commit()
""" % (PREV[0], PREV[0], PREV[1], PREV[2], PREV[4], PREV[4], PREV[5], PREV[5], PRICE0))
summary()
