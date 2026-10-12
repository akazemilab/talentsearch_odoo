#!/usr/bin/env python3
"""Clinic phase 4 (prepaid billing) over HTTP against a served CLONE:  ts_http_billing.py DB PORT

A prepaid counseling-center test panel with a known balance and an unpaid top-up invoice. The owner sees the credits page
(balance, held, this month, prices, invoices with the portal link) and sets a counselor's monthly cap; the counselor sees only
the own cap and the prices; the invitation wizard shows the price of each instrument and disables the one the panel cannot
afford; the cap and the insufficient-credit refusals are shown as the page error; the participant accepts, answers and sees
the result, and no participant page ever shows money words (تومان / ریال / اعتبار). Fixtures are committed on the clone (like
the other HTTP suites); nothing is sent (no SMS)."""
import os, re, sys, importlib.util

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
NAMES = ('owner', 'c1', 'p1')
L = {n: 'ts.bill.%s.http@example.invalid' % n for n in NAMES}
pw = {u: ensure_user(u) for u in L.values()}
FA = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
MONEY_WORDS = ('تومان', 'ریال', 'اعتبار')
# Rial. P2 is a real top-of-range price (۲۵۰٬۰۰۰ تومان) that is still above START - P1 and the counselor's cap room
# (G8-P4-2: the old 900,000,000 Rial showed «۹۰٬۰۰۰٬۰۰۰ تومان» in screenshots).
P1, P2, START = 1200000, 2500000, 3000000

code = r"""
from odoo import fields
Command = fields.Command
L = %r
P1, P2, START = %d, %d, %d
def user(n): return env['res.users'].search([('login', '=', L[n])])
small = env['ts.instrument'].search([('state', '=', 'published'), ('audience', '=', 'adult'), ('code', '=like', 'inventory_%%')]) \
    .sorted(lambda i: (i.active_item_count, i.id))[:2]
i1, i2 = small[0], small[1]
(i1 | i2)._ts_ensure_product()
i1.write({'ts_list_price': P1}); i2.write({'ts_list_price': P2})
name = 'پنل آزمون شارژ وب'
org = env['res.partner'].search([('name', '=', name)], limit=1) or env['res.partner'].create({'name': name, 'is_company': True})
ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create(
    {'name': name, 'purpose': 'clinical', 'partner_id': org.id, 'escalation_contact_id': org.id})
ws.write({'billing_mode': 'prepaid', 'catalog_mode': 'purpose'})
ws.state = 'active'
# an earlier run of this suite on the same clone may have left names carrying the forbidden word
for old in env['res.partner'].sudo().search([('name', 'like', 'آزمون اعتبار')]):
    old.name = old.name.replace('اعتبار', 'شارژ')
for ws_old in env['ts.workspace'].search([('name', 'like', 'آزمون اعتبار')]):
    ws_old.name = ws_old.name.replace('اعتبار', 'شارژ')
for asg in env['ts.assignment'].sudo().search([('invitee_name', 'like', 'آزمون اعتبار')]):
    asg.invitee_name = asg.invitee_name.replace('اعتبار', 'شارژ')
def member(n, role):
    u = user(n)
    m = env['ts.workspace.member'].with_context(active_test=False).search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)]) \
        or env['ts.workspace.member'].create({'workspace_id': ws.id, 'user_id': u.id, 'role': role})
    m.write({'active': True, 'role': role, 'monthly_cap': 0, 'catalog_restricted': False,
             'restrict_instrument_ids': [Command.clear()], 'restrict_battery_ids': [Command.clear()]})
    if role in ('clinician', 'clinic_director'):
        m.write({'license_number': 'T-1', 'verification_state': 'verified'})
    return m
mo = member('owner', 'owner'); m1 = member('c1', 'clinician')
open_ = env['ts.assignment'].sudo().search([('workspace_id', '=', ws.id), ('state', 'not in', ('done', 'withdrawn', 'declined'))])
for a in open_:
    if a.attempt_id.state != 'done':
        a.action_withdraw()
w = ws.ts_wallet()
avail = w.ts_available()
if avail != START:
    w.ts_adjust(START - avail, 'correction')
w.sudo().write({'low_threshold': 0, 'low_alert_sent_on': False})
inv = env['account.move'].search([('ts_workspace_id', '=', ws.id), ('ref', '=', 'TS-HTTP-BILLING')], limit=1)
if not inv:
    topup = env.ref('ts_billing.product_topup')
    inv = env['account.move'].create({'move_type': 'out_invoice', 'partner_id': org.id, 'ts_workspace_id': ws.id, 'ref': 'TS-HTTP-BILLING',
        'invoice_line_ids': [Command.create({'product_id': topup.id, 'quantity': 1, 'price_unit': 5000000, 'tax_ids': [Command.clear()]})]})
    inv.action_post()
env['ir.config_parameter'].sudo().set_str('ts_panel.invites_per_hour', '200')
spent = w.ts_month_spend(m1)
env.cr.commit()
print('IDS', ws.id, mo.id, m1.id, i1.id, i2.id, inv.id, spent)
print('INV', inv.name)
""" % (L, P1, P2, START)
out = shell(code)
mm = re.search(r'IDS (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)', out)
assert mm, out[-1500:]
WS, MO, M1, I1, I2, INV, SPENT = mm.groups()
SPENT = int(SPENT)
INV_NAME = re.search(r'^INV (.*)$', out, re.M).group(1).strip()
W = '/my/workspaces/%s' % WS


def toman(rial):
    return '{:,}'.format(rial // 10).replace(',', '٬').translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')) + ' تومان'


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


def input_tag(body, value):
    m = re.search(r'<input[^>]*name="instrument_id"[^>]*value="%s"[^>]*>' % value, body) \
        or re.search(r'<input[^>]*value="%s"[^>]*name="instrument_id"[^>]*>' % value, body)
    return m.group(0) if m else ''


def no_money(body):
    return [w for w in MONEY_WORDS if w in body]


own, c1, p1 = login('owner'), login('c1'), login('p1')

# ---------------------------------------------------------------- 1. the owner's credits page
st, body = get(own, W + '/credits')
check('owner: credits page with the three cards', st == 200 and 'موجودی قابل استفاده' in body and 'رزروشده برای دعوت‌های باز' in body
      and 'کسرشده این ماه' in body and toman(START) in body, str(st))
check('owner: price list with the instrument price', 'فهرست قیمت این پنل' in body and toman(P1) in body)
check('owner: the invoice with its portal link and state', INV_NAME in body and ('/my/invoices/%s?access_token=' % INV) in body
      and 'در انتظار پرداخت' in body)
check('owner: caps editor and threshold form', 'name="cap"' in body and ('name="member_id" value="%s"' % M1) in body and 'name="threshold"' in body)
cap = SPENT + P1 + 800000          # room for exactly one more invitation of P1
st, loc, _ = post(own, W + '/credits/cap', {'member_id': M1, 'cap': str(cap // 10)})
check('owner sets the counselor\'s monthly cap (typed in toman)', st in (302, 303) and '/credits' in loc, loc)
out = shell("print('CAP', int(env['ts.workspace.member'].browse(%s).monthly_cap))" % M1)
check('the cap is stored in Rial', ('CAP %d' % cap) in out, out[-200:])
st, _, _ = post(c1, W + '/credits/cap', {'member_id': M1, 'cap': '0'})
check('a counselor cannot change caps (403)', st == 403, str(st))

# ---------------------------------------------------------------- 2. the counselor's own page
st, body = get(c1, W + '/credits')
check('counselor: own cap and month, plus the prices', st == 200 and 'هزینهٔ دعوت‌های شما' in body and toman(cap) in body
      and 'فهرست قیمت این پنل' in body and toman(P1) in body, str(st))
check('counselor: no panel balance, no invoices', 'موجودی قابل استفاده' not in body and '/my/invoices/' not in body and INV_NAME not in body)
st, body = get(c1, W)
check('counselor dashboard: the cap bar links to the credits page', st == 200 and 'tsb-cap' in body and (W + '/credits') in body, str(st))
st, body = get(own, W)
check('owner dashboard: «اعتبار: … · رزروشده: …»', st == 200 and 'tsb-dash-credit' in body and 'رزروشده' in body, str(st))

# ---------------------------------------------------------------- 3. the wizard: prices, disabled item, review
get(c1, W + '/invites/new?fresh=1')
post(c1, W + '/invites/new', {'step': '1', 'new_name': 'مراجع آزمون شارژ', 'new_phone': '', 'new_email': '', 'new_age': 'adult'})
st, body = get(c1, W + '/invites/new?step=2')
t1, t2 = input_tag(body, I1), input_tag(body, I2)
check('wizard step 2: each item card shows «هزینه: … تومان»', st == 200 and 'هزینه: ' in body and toman(P1) in body and toman(P2) in body, str(st))
check('wizard step 2: the unaffordable item is disabled with the limit that stops it', 'disabled' in t2 and 'disabled' not in t1
      and ('اعتبار پنل برای این مورد کافی نیست' in body or 'از باقی‌ماندهٔ سقف ماهانهٔ شما' in body), '%s | %s' % (t1[:120], t2[:120]))
post(c1, W + '/invites/new', {'step': '2', 'instrument_id': I1})
post(c1, W + '/invites/new', {'step': '3', 'deadline': '', 'note': ''})
st, body = get(c1, W + '/invites/new?step=4')
check('wizard review shows the price before sending', st == 200 and 'tsb-review-price' in body and toman(P1) in body, str(st))
st, loc, _ = post(c1, W + '/invites/new', {'step': '4'})
m = re.search(r'/invites/(\d+)\?new=1', loc)
check('the first invitation is created', bool(m), loc)
AID = m.group(1) if m else '0'
out = shell("a = env['ts.assignment'].browse(%s); t = env['ts.wallet.txn'].search([('idem_key', '=', 'hold:%%d' %% a.id)]); print('HOLD', int(a.price_held), int(t.amount))" % AID)
check('server: the price is held', ('HOLD %d %d' % (P1, -P1)) in out, out[-200:])

# cap refusal shown as the page error, already at step 2 (the server refuses it again at creation: tests_billing H05)
get(c1, W + '/invites/new?fresh=1')
post(c1, W + '/invites/new', {'step': '1', 'new_name': 'مراجع دوم شارژ', 'new_phone': '', 'new_email': '', 'new_age': 'adult'})
st, loc, _ = post(c1, W + '/invites/new', {'step': '2', 'instrument_id': I1})
st, body = get(c1, path_of(loc) if loc else W + '/invites/new?step=2')
check('cap refusal at step 2: «هزینهٔ این دعوت (…) از باقی‌ماندهٔ سقف ماهانهٔ شما (…) بیشتر است … از مالک یا …»',
      'از باقی‌ماندهٔ سقف ماهانهٔ شما' in body and 'بخواهید سقف را بالا ببرد' in body and 'step=2' in (loc or ''), (loc or '')[:120])

# insufficient refusal (the owner is not capped; the expensive item is refused at step 2 with the balance and the next step;
# the creation-time refusal is tests_billing H01)
get(own, W + '/invites/new?fresh=1')
post(own, W + '/invites/new', {'step': '1', 'new_name': 'مراجع گران', 'new_phone': '', 'new_email': '', 'new_age': 'adult'})
st, loc, _ = post(own, W + '/invites/new', {'step': '2', 'instrument_id': I2})
st, body = get(own, path_of(loc) if loc else W + '/invites/new?step=2')
check('insufficient refusal: «اعتبار پنل برای این دعوت کافی نیست: موجودی قابل استفاده … است و هزینهٔ این دعوت ….»',
      'اعتبار پنل برای این دعوت کافی نیست: موجودی قابل استفاده %s است و هزینهٔ این دعوت %s.' % (toman(START - P1), toman(P2)) in body
      and 'step=2' in (loc or ''), (loc or '')[:120])
check('owner: the top-up request link on the credits page', ('/contact?topic=credit&amp;panel=' in get(own, W + '/credits')[1]))

# ---------------------------------------------------------------- 4. the participant never sees money words
st, body = get(c1, W + '/invites/%s' % AID)
tok = re.search(r'/invite/([0-9a-f]{32})', body)
TOKEN = tok.group(1) if tok else 'x'
st, body = get(p1, '/invite/' + TOKEN)
check('participant: invitation page has no money words', st == 200 and not no_money(body), '%s %s' % (st, no_money(body)))
st, loc, _ = post(p1, '/invite/%s/accept' % TOKEN, {'share': '1'})
T = re.search(r'/take/([0-9a-f]+)', loc or '')
T = T.group(1) if T else 'x'
st, body = get(p1, '/take/' + T)
check('participant: consent page has no money words', st == 200 and not no_money(body), '%s %s' % (st, no_money(body)))
post(p1, '/take/%s/consent' % T, {'consent_service': '1'})
st, page = get(p1, '/take/' + T)
check('participant: player has no money words', st == 200 and not no_money(page), '%s %s' % (st, no_money(page)))
m = re.search(r'صفحهٔ [۰-۹]+ از ([۰-۹]+)', page)
pages = int(m.group(1).translate(FA)) if m else 1
csrf = p1.csrf(page)
for pg in range(1, pages + 1):
    st, page = get(p1, '/take/%s?page=%d' % (T, pg))
    for iid in re.findall(r'class="ts-q" data-item="(\d+)"', page):
        p1.req('/take/%s/answer' % T, {'csrf_token': csrf, 'item': iid, 'value': str(1 + int(iid) % 5)})
st, body = get(p1, '/take/%s/review' % T)
check('participant: review page has no money words', st == 200 and not no_money(body), '%s %s' % (st, no_money(body)))
st, loc, _ = post(p1, '/take/%s/submit' % T, {'submission_key': T})
st, body = get(p1, path_of(loc) if loc else '/my/assessments')
check('participant: result / transition page has no money words', st == 200 and not no_money(body), '%s %s %s' % (st, (loc or '')[:80], no_money(body)))
for path in ('/my', '/my/assessments'):
    st, body = get(p1, path)
    hits = no_money(body)
    if hits:
        i = body.find(hits[0]); print('FAIL ctx ' + body[max(0, i - 160):i + 60].replace('\n', ' '))
    check('participant: %s has no money words' % path, st == 200 and not hits, '%s %s' % (st, hits))
out = shell("a = env['ts.assignment'].browse(%s); at = a.attempt_id; t = env['ts.wallet.txn']; "
            "print('CONV', at.state, int(t.search([('idem_key', '=', 'release:%%d' %% a.id)]).amount), int(t.search([('idem_key', '=', 'usage:%%d' %% at.id)]).amount))" % AID)
check('server: completion converted the hold (release + debit)', ('CONV done %d %d' % (P1, -P1)) in out, out[-200:])

# ---------------------------------------------------------------- 5. eot.ir has no billing pages
e = Client('www.eot.ir'); e.login(L['owner'], pw[L['owner']])
check('eot.ir has no panel credits page', e.req(W + '/credits')[0] == 404)
summary()
