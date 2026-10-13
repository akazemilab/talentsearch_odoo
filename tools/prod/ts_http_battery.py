#!/usr/bin/env python3
"""Clinic phase 3 (battery run) over HTTP against a served CLONE:  ts_http_battery.py DB PORT

Owner of a counseling-center test panel (granted catalog) gives one counselor one battery on the member page; the counselor
invites a participant to that battery through the wizard; the participant accepts, sees ONE consent page listing the
instruments, answers every instrument through the existing POST routes, sees the transition page, then the battery result
page with one section per instrument; the counselor opens the panel battery page; a second counselor without access gets a
404. Fixtures are committed on the clone (like the other HTTP suites); nothing is sent (no SMS)."""
import os, re, sys, importlib.util

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
lib.fake_kavenegar()     # clones never text anyone: any SMS of these flows goes to a local fake gateway
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
NAMES = ('owner', 'c1', 'c2', 'p1')
L = {n: 'ts.bat.%s.http@example.invalid' % n for n in NAMES}
pw = {u: ensure_user(u) for u in L.values()}
FA = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')

code = r"""
from odoo import fields
Command = fields.Command
L = %r
def user(n): return env['res.users'].search([('login', '=', L[n])])
B = env['ts.battery'].sudo()
bat = B.search([('code', '=', 'BAT-TEST-HTTP')], limit=1)
if not bat:
    small = env['ts.instrument'].search([('state', '=', 'published'), ('audience', '=', 'adult'), ('code', '=like', 'inventory_%%')]) \
        .sorted(lambda i: (i.active_item_count, i.id))[:2]
    bat = B.create({'code': 'BAT-TEST-HTTP', 'name': 'آزمون وب', 'audience': 'adult', 'for_clinical': True,
                    'description': 'برای آزمون خودکار. این مجموعه برای کمک به گفت‌وگوی مشاوره است، نه تشخیص.',
                    'line_ids': [Command.create({'sequence': 10 * (n + 1), 'instrument_id': i.id}) for n, i in enumerate(small)]})
if bat.state != 'published':
    bat.action_publish()
intake = B.search([('code', '=', 'BAT-INTAKE-1')], limit=1)
name = 'پنل آزمون مجموعه وب'
org = env['res.partner'].search([('name', '=', name)], limit=1) or env['res.partner'].create({'name': name, 'is_company': True})
org.write({'is_company': True})
ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create(
    {'name': name, 'purpose': 'clinical', 'partner_id': org.id, 'escalation_contact_id': org.id})
ws.write({'catalog_mode': 'granted',
          'catalog_battery_ids': [Command.set((bat | intake).ids)]})
ws.state = 'active'
def member(n, role):
    u = user(n)
    m = env['ts.workspace.member'].with_context(active_test=False).search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)]) \
        or env['ts.workspace.member'].create({'workspace_id': ws.id, 'user_id': u.id, 'role': role})
    m.write({'active': True, 'role': role, 'catalog_restricted': False, 'restrict_instrument_ids': [Command.clear()],
             'restrict_battery_ids': [Command.clear()]})
    if role in ('clinician', 'clinic_director'):
        m.write({'license_number': 'T-1', 'verification_state': 'verified'})
    return m
mo = member('owner', 'owner'); m1 = member('c1', 'clinician'); m2 = member('c2', 'clinician')
env['ts.assignment'].sudo().search([('workspace_id', '=', ws.id), ('state', 'not in', ('done', 'withdrawn'))]).write({'withdrawn': True})
env['ir.config_parameter'].sudo().set_str('ts_panel.invites_per_hour', '200')
env.cr.commit()
print('IDS', ws.id, mo.id, m1.id, m2.id, bat.id, intake.id or 0, len(bat.line_ids))
print('NAMES', '|'.join(bat.line_ids.sorted('sequence').mapped('instrument_id.title')))
""" % L
out = shell(code)
mm = re.search(r'IDS (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)', out)
assert mm, out[-1500:]
WS, MO, M1, M2, BAT, INTAKE, NLINES = mm.groups()
INST_TITLES = re.search(r'^NAMES (.*)$', out, re.M).group(1).split('|')
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


def post(c, path, data):
    pairs = list(data.items()) if isinstance(data, dict) else list(data)
    pairs.append(('csrf_token', c.csrf(c.req('/web/login')[2])))
    return c.req(path, pairs)


def fa2int(s):
    return int(s.translate(FA))


own, c1, c2, p1 = login('owner'), login('c1'), login('c2'), login('p1')

# ---------------------------------------------------------------- 1. the owner grants c1 one battery on the member page
st, body = get(own, W + '/members/%s' % M1)
check('owner sees the catalog section on the counselor\'s page', st == 200 and 'سنجه‌ها و مجموعه‌های مجاز برای این عضو' in body
      and 'name="battery_ids"' in body and 'همهٔ موارد پنل' in body, str(st))
st, loc, _ = post(own, W + '/members/%s/catalog' % M1, [('catalog_mode', 'list'), ('battery_ids', BAT)])
check('saving the checklist redirects back to the member page', st in (302, 303) and ('/members/%s' % M1) in loc, loc)
st, body = get(own, W + '/members/%s' % M1)
check('the page now names the one allowed battery', st == 200 and 'فقط «آزمون وب»' in body)
out = shell("m = env['ts.workspace.member'].browse(%s); print('CAT', int(m.catalog_restricted), sorted(m.allowed_batteries().ids), len(m.allowed_instruments()),"
            " env['ts.audit.event'].search_count([('event_type', '=', 'catalog.change'), ('res_model', '=', 'ts.workspace.member'), ('res_id', '=', m.id)]))" % M1)
cat = re.search(r'CAT (\d) \[([\d, ]*)\] (\d+) (\d+)', out)
check('server state: restricted to exactly that battery, no instrument, audited',
      cat and cat.group(1) == '1' and cat.group(2).strip() == BAT and cat.group(3) == '0' and int(cat.group(4)) >= 1, out[-300:])
st, loc, _ = post(own, W + '/members/%s/catalog' % M1, [('catalog_mode', 'list'), ('battery_ids', '999999')])
out = shell("m = env['ts.workspace.member'].browse(%s); print('CAT2', sorted(m.allowed_batteries().ids))" % M1)
check('an id outside the panel catalog is refused by the server (nothing changes)', ('CAT2 [%s]' % BAT) in out, out[-200:])
st, _, _ = post(c1, W + '/members/%s/catalog' % M2, [('catalog_mode', 'all')])
check('a counselor cannot change a colleague\'s catalog (403)', st == 403, str(st))

# ---------------------------------------------------------------- 2. c1 invites a participant to the battery
get(c1, W + '/invites/new?fresh=1')
post(c1, W + '/invites/new', {'step': '1', 'new_name': 'مراجع آزمون مجموعه', 'new_phone': '', 'new_email': '', 'new_age': 'adult'})
st, body = get(c1, W + '/invites/new?step=2')
check('wizard step 2 offers the granted battery card (a member without single instruments gets no «یک سنجه» choice)',
      st == 200 and 'name="item_kind" value="battery"' in body and 'value="single"' not in body
      and ('name="battery_id" value="%s"' % BAT) in body and ('name="battery_id" value="%s"' % INTAKE) not in body and 'سنجه، ' in body, str(st))
st, loc, _ = post(c1, W + '/invites/new', {'step': '2', 'item_kind': 'battery', 'battery_id': INTAKE})
check('a battery outside the counselor\'s list is refused at step 2', st in (302, 303) and 'step=2' in loc, loc)
st, loc, _ = post(c1, W + '/invites/new', {'step': '2', 'item_kind': 'battery', 'battery_id': BAT})
check('choosing the granted battery moves to step 3', st in (302, 303) and 'step=3' in loc, loc)
post(c1, W + '/invites/new', {'step': '3', 'deadline': '', 'note': ''})
st, body = get(c1, W + '/invites/new?step=4')
check('the review names the battery', st == 200 and '<dt>مجموعه</dt>' in body and 'آزمون وب' in body, str(st))
st, loc, _ = post(c1, W + '/invites/new', {'step': '4'})
m = re.search(r'/invites/(\d+)\?new=1', loc)
check('creating the invitation opens its page', bool(m), loc)
AID = m.group(1) if m else '0'
st, body = get(c1, W + '/invites/%s' % AID)
tok = re.search(r'/invite/([0-9a-f]{32})', body)
check('the invitation page shows the link and the battery name', st == 200 and bool(tok) and 'مجموعهٔ آزمون وب' in body, str(st))
TOKEN = tok.group(1) if tok else 'x'

# ---------------------------------------------------------------- 3. the participant: accept, one consent page, answer, transition
st, body = get(p1, '/invite/' + TOKEN)
check('the participant\'s invitation page names the battery and lists its instruments',
      st == 200 and 'مجموعهٔ آزمون وب' in body and all(t in body for t in INST_TITLES), str(st))
check('...with size and time first (UX T7 X5: «N سنجه: M پرسش» and the battery estimate) and the instant-result promise',
      'id="ts-invite-facts"' in body and 'سنجه: ' in body and 'نتیجه بلافاصله پس از پایان آماده است' in body
      and body.index('id="ts-invite-facts"') < body.index('/accept'), str(st))
st, loc, _ = post(p1, '/invite/%s/accept' % TOKEN, {'share': '1'})
check('accept -> /take/<first token>', st in (302, 303) and '/take/' in loc, loc)
out = shell("a = env['ts.assignment'].browse(%s); print('ATT', ' '.join('%%s:%%s' %% (t.id, t.access_token) for t in a.ts_battery_attempts()), a.client_id.id)" % AID)
att = re.search(r'ATT ((?:\d+:[0-9a-f]+ ?)+) (\d+)', out)
pairs = [x.split(':') for x in att.group(1).split()] if att else []
CID = att.group(2) if att else '0'
check('accept created one attempt per instrument', len(pairs) == int(NLINES), out[-300:])
T = [p[1] for p in pairs]
IDS = [p[0] for p in pairs]
st, body = get(p1, '/take/' + T[0])
check('ONE consent page: names the battery, lists every instrument with the total time',
      st == 200 and 'consent_service' in body and 'این دعوت یک مجموعه است' in body and all(t in body for t in INST_TITLES)
      and 'روی هم' in body and 'TS-CONSENT-1405-07-21-v6' in body, str(st))
# CONSENT v5 plain language (owner 2026-10-13): the summary names the whole battery; the card opens the folded full text
check('v5: the summary says one agreement covers the whole battery, then the full text follows behind one button',
      'id="ts-consent-summary"' in body and 'یک بار موافقت در همین صفحه برای همه کافی است' in body and 'برای همهٔ مجموعه' in body
      and body.find('id="ts-consent-summary"') < body.find('aria-controls="ts-consent-more"') < body.find('این دعوت یک مجموعه است'))
st, loc, _ = p1.req('/take/' + T[1])
check('a sibling never shows its own consent page (redirect to the first)', st in (302, 303) and T[0] in loc, '%s %s' % (st, loc))
post(p1, '/take/%s/consent' % T[0], {'consent_service': '1'})
st, loc, _ = p1.req('/take/' + T[1])
check('after consent the second instrument waits for the first (redirect to it)', st in (302, 303) and T[0] in loc, '%s %s' % (st, loc))


def answer_all(c, token):
    st, page = get(c, '/take/' + token)
    m = re.search(r'صفحهٔ [۰-۹]+ از ([۰-۹]+)', page)
    pages = fa2int(m.group(1)) if m else 1
    csrf = c.csrf(page)
    n = 0
    for p in range(1, pages + 1):
        st, page = get(c, '/take/%s?page=%d' % (token, p))
        for iid in re.findall(r'class="ts-q" data-item="(\d+)"', page):
            st, _, body = c.req('/take/%s/answer' % token, {'csrf_token': csrf, 'item': iid, 'value': str(1 + int(iid) % 5)})
            n += st == 200
    return n, page


n, page = answer_all(p1, T[0])
check('the player header shows the battery position (instrument 1 of N)', 'سنجهٔ ۱ از' in page and 'مجموعهٔ آزمون وب' in page)
st, body = get(p1, '/take/%s/review' % T[0])
check('the review of a non-last instrument says «ارسال و رفتن به سنجهٔ بعدی»', st == 200 and 'ارسال و رفتن به سنجهٔ بعدی' in body)
st, loc, _ = post(p1, '/take/%s/submit' % T[0], {'submission_key': T[0]})
check('submitting instrument 1 goes to the transition page', st in (302, 303) and loc.endswith('/take/%s/next' % T[0]), loc)
st, body = get(p1, '/take/%s/next' % T[0])
check('transition: «سنجهٔ ۱ از N تمام شد», the next instrument, continue and later',
      st == 200 and 'سنجهٔ ۱ از' in body and 'تمام شد' in body and INST_TITLES[1] in body and ('/take/%s' % T[1]) in body
      and 'بعداً ادامه می‌دهم' in body and 'href="/my"' in body, str(st))
st, body = get(p1, '/my/assessments')
check('/my/assessments shows the battery as one row with progress', st == 200 and 'مجموعهٔ آزمون وب' in body
      and ('۱ از %s سنجه انجام شده' % NLINES.translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))) in body
      and ('/my/assessments/%s"' % IDS[0]) not in body, str(st))
st, body = get(p1, '/my')
check('/my shows the battery as the one next step', st == 200 and 'مجموعهٔ آزمون وب' in body and 'سنجه انجام شده' in body, str(st))
for i in range(1, len(T)):
    n, page = answer_all(p1, T[i])
    check('instrument %d: answered through the autosave route (%d answers)' % (i + 1, n), n > 0)
    st, loc, _ = post(p1, '/take/%s/submit' % T[i], {'submission_key': T[i]})
    if i < len(T) - 1:
        check('instrument %d -> transition' % (i + 1), loc.endswith('/take/%s/next' % T[i]), loc)
    else:
        check('the last instrument -> the battery result page', ('/my/assessments/battery/%s' % AID) in loc, loc)

# ---------------------------------------------------------------- 4. the battery result page (participant)
st, body = get(p1, '/my/assessments/battery/%s?submitted=1' % AID)
check('battery result page: header, one section per instrument, jump links, collapsible sections',
      st == 200 and body.count('tt-sec tsb-sec') == int(NLINES) and 'tsb-jump' in body and 'aria-expanded' in body
      and 'data-collapse="phone"' in body and all(t in body for t in INST_TITLES), str(st))
check('the battery page reuses the report blocks (summary, bands, texts) and says «نه تشخیص»',
      'خلاصهٔ نتیجه‌ها' in body and 'ts-band' in body and 'برای کمک به گفت‌وگوی مشاوره است، نه تشخیص' in body and 'نمای کلی مجموعه' in body)
check('the battery page shows the counseling center and has a print button', 'پنل آزمون مجموعه وب' in body and 'ts-js-print' in body)
st, body = get(p1, '/my/assessments')
check('/my/assessments lists the finished battery as one row linking to its page', ('/my/assessments/battery/%s' % AID) in body)
st, loc, _ = p1.req('/take/' + T[0])
check('a finished battery attempt opens the battery page', st in (302, 303) and ('/my/assessments/battery/%s' % AID) in loc, loc)

# ---------------------------------------------------------------- 5. the panel side
B_URL = W + '/clients/%s/b/%s' % (CID, AID)
st, body = get(c1, W + '/clients/%s' % CID)
check('the panel participant page lists the battery as one row with its result link', st == 200 and B_URL in body and 'نتیجهٔ مجموعه' in body, str(st))
n0 = shell("print('N', env['ts.audit.event'].search_count([('event_type', '=', 'result.view'), ('res_model', '=', 'ts.assignment'), ('res_id', '=', %s)]))" % AID)
st, body = get(c1, B_URL)
check('the counselor opens the panel battery page: one section per instrument at level clinical',
      st == 200 and body.count('tt-sec tsb-sec') == int(NLINES) and 'نمره (۱ تا ۵)' in body and 'گزارش ویژهٔ مشاور' in body, str(st))
n1 = shell("print('N', env['ts.audit.event'].search_count([('event_type', '=', 'result.view'), ('res_model', '=', 'ts.assignment'), ('res_id', '=', %s)]))" % AID)
a0 = re.search(r'N (\d+)', n0); a1 = re.search(r'N (\d+)', n1)
check('each opening is audited as result.view', a0 and a1 and int(a1.group(1)) == int(a0.group(1)) + 1)
st, _ = get(c2, B_URL)
check('a second counselor without access gets 404', st == 404, str(st))
st, _ = get(own, B_URL)
check('the owner (not practising) gets the status page only', st == 200)
e = Client('www.eot.ir'); e.login(L['c1'], pw[L['c1']])
check('eot.ir has no battery pages', e.req(B_URL)[0] == 404 and e.req('/my/assessments/battery/%s' % AID)[0] == 404)
check('another participant cannot open this battery page', get(own, '/my/assessments/battery/%s' % AID)[0] == 404)
summary()
