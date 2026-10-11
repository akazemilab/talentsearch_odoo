# Clinic phase 4 (ts_billing): products, prices, hold / release / charge, caps, top-up invoices, currency switch, reconcile.
# Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits (rolls back at the end); savepoints inside.
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.addons.ts_billing.models.campaign import JOIN_FULL, OPEN_LINK_FLOOR
from odoo.addons.ts_billing.models.wallet import CAP_FULL, INSUFFICIENT
from odoo.addons.ts_billing.tools import fa_num, fmt_toman, jalali_month_bounds

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []
Command = fields.Command


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def raises(fn, exc):
    try:
        with env.cr.savepoint():
            fn()
    except exc:
        return True
    except Exception as e:
        print('    unexpected', type(e).__name__, str(e)[:160])
        return False
    return False


def refused(fn):
    """Call fn WITHOUT an outer savepoint (the code under test rolls its own work back); -> the UserError text or ''."""
    try:
        fn()
    except UserError as e:
        return str(e.args[0]) if e.args else str(e)
    return ''


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, A, B, Inst = env['ts.workspace'], env['ts.workspace.member'], env['ts.assignment'], env['ts.battery'], env['ts.instrument']
Txn, Audit, N = env['ts.wallet.txn'], env['ts.audit.event'], env['ts.notification']
_n = [0]


def puser(tag='u'):
    _n[0] += 1
    login = 'ts.bill.%s%d@example.invalid' % (tag, _n[0])
    return U.create({'name': login, 'login': login, 'email': login, 'group_ids': [Command.set([portal.id])]})


def panel(purpose='clinical', mode='prepaid', name=None):
    org = env['res.partner'].create({'name': name or ('پنل آزمون اعتبار %d' % (_n[0] + 1)), 'is_company': True})
    _n[0] += 1
    vals = {'name': org.name, 'purpose': purpose, 'partner_id': org.id}
    if purpose == 'clinical':
        vals['escalation_contact_id'] = org.id
    ws = W.create(vals)
    ws.write({'approved_on': '2026-01-01 00:00:00'})
    ws.state = 'pilot'
    if mode == 'prepaid':
        ws.billing_mode = 'prepaid'
    return ws


def member(ws, role):
    m = M.create({'workspace_id': ws.id, 'user_id': puser(role).id, 'role': role})
    if role in ('clinician', 'clinic_director', 'counselor'):
        m.write({'license_number': 'T-%d' % m.id, 'verification_state': 'verified'})
    return m


def invite(ws, by, inst=None, bat=None, name='مراجع آزمون اعتبار'):
    vals = {'workspace_id': ws.id, 'invitee_name': name, 'invited_by_id': by.user_id.id}
    if bat:
        vals['battery_id'] = bat.id
    else:
        vals['instrument_id'] = inst.id
    return A.create(vals)


def finish(at):
    if at.state == 'consent':
        at.give_consent(research=False, role='self')
    for it in at.active_items():
        at.save_answer(it.id, 1 + it.id % 5)
    return at.action_submit()


def rows(ws, **kw):
    dom = [('workspace_id', '=', ws.id)] + [(k, '=', v) for k, v in kw.items()]
    return Txn.search(dom)


def key(k):
    return Txn.search([('idem_key', '=', k)])


# ---------------------------------------------------------------- 0. currency (install switched USD -> IRR on a clean eot_main)
company = env['res.company'].browse(1)
irr = env.ref('base.IRR')
check('C01 company 1 currency is IRR after install', company.currency_id == irr, company.currency_id.name)
check('C01 IRR: rounding 1, no decimals, symbol after', irr.rounding == 1.0 and irr.decimal_places == 0 and irr.position == 'after',
      '%s %s %s' % (irr.rounding, irr.decimal_places, irr.position))
check('C02 the switch function is idempotent (already IRR)', env['ts.wallet']._ts_switch_company_currency() == 'already')
usd = env.ref('base.USD')
verdict, still_usd = None, False
try:
    with env.cr.savepoint():
        env.cr.execute('UPDATE res_company SET currency_id = %s WHERE id = 1', [usd.id])
        env.invalidate_all()
        misc = env['account.journal'].search([('type', '=', 'general'), ('company_id', '=', 1)], limit=1)
        env['account.move'].create({'move_type': 'entry', 'journal_id': misc.id})
        verdict = env['ts.wallet']._ts_switch_company_currency()
        env.invalidate_all()
        still_usd = env['res.company'].browse(1).currency_id.name == 'USD'
        raise UserError('rollback')
except UserError:
    pass
env.invalidate_all()
check('C03 the switch is skipped (no exception) when a journal entry exists', verdict == 'skipped:accounting' and still_usd, str(verdict))
check('C03 the savepoint left IRR in place', env['res.company'].browse(1).currency_id == irr)

# ---------------------------------------------------------------- 1. products
categ = env.ref('ts_billing.product_category_instruments')
pub = Inst.search([('state', '=', 'published')])
missing = pub.filtered(lambda i: not i.product_id)
check('P01 every published instrument has a product', not missing, str(missing.mapped('code')[:5]))
bad = [i.code for i in pub if i.product_id and not (
    i.product_id.type == 'service' and i.product_id.sale_ok and not i.product_id.purchase_ok and i.product_id.default_code == i.code
    and i.product_id.categ_id == categ and not i.product_id.taxes_id and i.product_id.product_tmpl_id.ts_instrument_id == i)]
check('P02 product: service, sold, not purchased, code, category «استعدادیاب / سنجه‌ها», no taxes, linked', not bad, str(bad[:5]))
check('P02 category path', categ.complete_name == 'استعدادیاب / سنجه‌ها', categ.complete_name)
topup = env.ref('ts_billing.product_topup')
check('P03 top-up product: service, flagged, no taxes, price 0', topup.type == 'service' and topup.ts_topup and not topup.taxes_id
      and topup.list_price == 0 and topup.name == 'اعتبار پیش‌پرداخت استعدادیاب')
check('P04 product sync is idempotent', Inst._ts_sync_all_products() == 0 and B._ts_sync_all_products() == 0)

small = Inst.search([('state', '=', 'published'), ('audience', '=', 'adult'), ('code', '=like', 'inventory_%')]) \
    .sorted(lambda i: (i.active_item_count, i.id))[:3]
i1 = small[0]
bat = B.create({'code': 'BAT-TEST-BILL', 'name': 'مجموعهٔ آزمون اعتبار', 'audience': 'adult', 'for_clinical': True,
                'line_ids': [Command.create({'sequence': 10 * (n + 1), 'instrument_id': i.id}) for n, i in enumerate(small[1:3])]})
check('P05 a draft battery has no product yet', not bat.product_id)
bat.action_publish()
check('P05 publishing a battery creates its product', bat.product_id and bat.product_id.product_tmpl_id.ts_battery_id == bat
      and bat.product_id.default_code == 'BAT-TEST-BILL')
bat.name = 'مجموعهٔ آزمون اعتبار (نام تازه)'
check('P06 renaming a battery renames its product', bat.product_id.name == 'مجموعهٔ آزمون اعتبار (نام تازه)', bat.product_id.name)
old_name = i1.name
i1.name = old_name + ' (آزمون)'
check('P06 renaming an instrument renames its product', i1.product_id.name == old_name + ' (آزمون)')
i1.name = old_name
check('P07 a price that is not a multiple of 10 Rial is refused', raises(lambda: i1.write({'ts_list_price': 1200005}), ValidationError))
i1.write({'ts_list_price': 1200000})
bat.write({'ts_list_price': 3000000})
check('P08 «قیمت پایه (ریال)» edits the product list price', i1.product_id.list_price == 1200000 and bat.product_id.list_price == 3000000)
P1, PB = 1200000, 3000000

# ---------------------------------------------------------------- 2. prices per panel
ws = panel()
own, dire, c1, c2 = member(ws, 'owner'), member(ws, 'clinic_director'), member(ws, 'clinician'), member(ws, 'clinician')
check('W01 billing.mode audited', Audit.search_count([('event_type', '=', 'billing.mode'), ('workspace_id', '=', ws.id)]) == 1)
check('R01 default price = list price', ws.ts_price(i1.product_id) == P1 and ws.ts_price(bat.product_id) == PB)
ws_pl = panel()
pl = env['product.pricelist'].create({'name': 'قیمت ویژهٔ آزمون', 'currency_id': irr.id,
                                      'item_ids': [Command.create({'applied_on': '0_product_variant', 'product_id': i1.product_id.id,
                                                                   'compute_price': 'fixed', 'fixed_price': 900000})]})
# the partner form's «Pricelist» stores this field when it differs from Odoo's fallback (the first pricelist); ts_price reads it
ws_pl.partner_id.specific_property_product_pricelist = pl
check('R02 a pricelist set on the institution gives its own price', ws_pl.ts_price(i1.product_id) == 900000, str(ws_pl.ts_price(i1.product_id)))
check('R03 another panel keeps the list price (no fallback to someone else\'s pricelist)', ws.ts_price(i1.product_id) == P1)
check('R04 fmt_toman: Persian digits, U+066C, تومان', fmt_toman(12000000) == '۱٬۲۰۰٬۰۰۰ تومان' and fmt_toman(0) == '۰ تومان', fmt_toman(12000000))

# ---------------------------------------------------------------- 3. hold / insufficient / cap
w = ws.ts_wallet()
n0 = A.search_count([('workspace_id', '=', ws.id)])
msg = refused(lambda: invite(ws, c1, i1))
check('H01 insufficient credit: exact message', msg == INSUFFICIENT % (fmt_toman(0), fmt_toman(P1)), msg)
check('H01 the refused invitation does not exist', A.search_count([('workspace_id', '=', ws.id)]) == n0)
check('H01 credit.refused audited (kind insufficient)', Audit.search_count([('event_type', '=', 'credit.refused'), ('workspace_id', '=', ws.id),
                                                                           ('detail', 'ilike', 'insufficient')]) == 1)
check('H02 a grant that is not a multiple of 10 is refused', raises(lambda: w.ts_grant(1005, 'manual'), UserError))
w.ts_grant(5000000, 'manual')
check('H02 grant: available 5,000,000', w.ts_available() == 5000000)
a1 = invite(ws, c1, i1)
check('H03 hold: one row of -price, price_held and product set', key('hold:%d' % a1.id).amount == -P1 and a1.price_held == P1
      and a1.priced_product_id == i1.product_id, str(a1.price_held))
check('H03 available and held', w.ts_available() == 5000000 - P1 and w.ts_held() == P1, '%s %s' % (w.ts_available(), w.ts_held()))
check('H03 credit.hold audited', Audit.search_count([('event_type', '=', 'credit.hold'), ('res_id', '=', a1.id), ('res_model', '=', 'ts.assignment')]) == 1)
c1.ts_set_cap(own, 2000000)
check('H04 cap change audited', Audit.search_count([('event_type', '=', 'credit.cap_change'), ('workspace_id', '=', ws.id)]) == 1)
check('H04 committed this month = the held price', w.ts_month_spend(c1) == P1)
msg = refused(lambda: invite(ws, c1, i1, name='دوم'))
check('H05 cap refusal: exact message', msg == CAP_FULL % (fmt_toman(P1), fmt_toman(2000000)), msg)
check('H05 credit.refused audited (kind cap)', Audit.search_count([('event_type', '=', 'credit.refused'), ('workspace_id', '=', ws.id),
                                                                   ('detail', 'ilike', '"cap"')]) == 1)
a_dir = invite(ws, dire, i1, name='مدیر')
check('H06 a director is never capped', bool(a_dir.price_held == P1))
check('H07 caps only for capped roles; only credits:manage sets them',
      raises(lambda: dire.ts_set_cap(own, 1000000), UserError) and raises(lambda: c2.ts_set_cap(c1, 1000000), UserError)
      and raises(lambda: c2.ts_set_cap(own, 1005), UserError))
check('H08 credits:manage = owner, admin, clinic_director, hr_admin',
      own.has_perm('credits:manage') and dire.has_perm('credits:manage') and not c1.has_perm('credits:manage'))

# ---------------------------------------------------------------- 4. charge at completion (single)
pu1 = puser('p')
at1 = a1.action_accept(pu1, share=True)
finish(at1)
check('D01 completion: release(+price) then debit(-price, 1 unit) on the attempt',
      key('release:%d' % a1.id).amount == P1 and key('usage:%d' % at1.id).amount == -P1 and key('usage:%d' % at1.id).units == 1)
check('D01 available unchanged by the conversion, held down', w.ts_available() == 5000000 - 2 * P1 and w.ts_held() == P1,
      '%s %s' % (w.ts_available(), w.ts_held()))
check('D01 the month spend of the counselor still counts the invitation', w.ts_month_spend(c1) == P1, str(w.ts_month_spend(c1)))
check('D01 credit.debit audited', Audit.search_count([('event_type', '=', 'credit.debit'), ('res_id', '=', a1.id)]) == 1)
w._debit_usage(at1)
check('D02 debit is idempotent', len(Txn.search([('assignment_id', '=', a1.id)])) == 3)

# ---------------------------------------------------------------- 5. battery: the first attempt converts, later ones debit 0
w.ts_grant(5000000, 'manual')
ab = invite(ws, dire, bat=bat, name='مراجع مجموعه')
check('D03 a battery holds the battery price', ab.price_held == PB and key('hold:%d' % ab.id).amount == -PB)
ab.action_accept(puser('p'), share=True)
atts = ab.ts_battery_attempts()
finish(atts[0])
check('D03 the first attempt to finish converts the whole price', key('usage:%d' % atts[0].id).amount == -PB and key('release:%d' % ab.id).amount == PB)
for t in atts[1:]:
    finish(t)
check('D03 later attempts: debit 0, 1 unit', all(key('usage:%d' % t.id).amount == 0 and key('usage:%d' % t.id).units == 1 for t in atts[1:]))

# ---------------------------------------------------------------- 6. release: withdraw, decline, expiry (once)
aw = invite(ws, own, i1, name='لغو')
aw.action_withdraw()
check('E01 withdraw releases the hold', key('release:%d' % aw.id).amount == P1)
aw._ts_billing_release('withdraw')
check('E01 a second release changes nothing', len(Txn.search([('assignment_id', '=', aw.id), ('type', '=', 'release')])) == 1)
ad = invite(ws, own, i1, name='رد')
ad.action_decline(puser('p'))
check('E02 decline releases the hold', key('release:%d' % ad.id).amount == P1)
ae = invite(ws, own, i1, name='منقضی')
aacc = invite(ws, own, i1, name='پذیرفته')
aacc.action_accept(puser('p'), share=True)
past = fields.Datetime.now() - timedelta(days=1)
(ae | aacc).write({'expires_at': past})
A._cron_release_expired_holds()
A._cron_release_expired_holds()
check('E03 expiry cron releases an unaccepted expired invitation once (cron twice = same state)',
      len(Txn.search([('assignment_id', '=', ae.id), ('type', '=', 'release')])) == 1 and key('release:%d' % ae.id).reason_code == 'expiry')
check('E04 an accepted invitation is never released by the cron', not key('release:%d' % aacc.id))

# ---------------------------------------------------------------- 7. void refund
check('V01 void dialog amount: a single attempt gives back its debit', at1.ts_void_refund() == P1)
check('V01 void dialog amount: a later battery attempt gives back 0', atts[1].ts_void_refund() == 0)
wiz = env['ts.attempt.void.wizard'].create({'attempt_id': at1.id, 'reason': 'technical'})
check('V02 the void dialog says «بازگشت اعتبار: …»', wiz.refund_text.startswith('بازگشت اعتبار: %s' % fmt_toman(P1)), wiz.refund_text)
before = w.ts_available()
wiz.action_confirm()
check('V03 void refunds exactly the debit', key('refund:%d' % at1.id).amount == P1 and w.ts_available() == before + P1)

# ---------------------------------------------------------------- 8. top-up by invoice
Move = env['account.move']


def topup_invoice(amount, ctx=None):
    inv = Move.with_context(**(ctx or {})).create({
        'move_type': 'out_invoice', 'partner_id': ws.partner_id.id, 'ts_workspace_id': ws.id,
        'invoice_line_ids': [Command.create({'product_id': topup.id, 'quantity': 1, 'price_unit': amount, 'tax_ids': [Command.clear()]})]})
    inv.with_context(**(ctx or {})).action_post()
    return inv


def pay(move, ctx=None):
    wz = env['account.payment.register'].with_context(active_model='account.move', active_ids=move.ids, **(ctx or {})).create({})
    wz.action_create_payments()
    move.invalidate_recordset()


check('T00 the invoice partner must be the panel\'s institution',
      raises(lambda: Move.create({'move_type': 'out_invoice', 'partner_id': ws_pl.partner_id.id, 'ts_workspace_id': ws.id}), ValidationError))
inv = topup_invoice(10000000)
check('T01 a posted, unpaid invoice credits nothing', not key('topup:%d' % inv.id))
before = w.ts_available()
pay(inv)
check('T02 paying the invoice credits the wallet once with the top-up amount', inv.payment_state in ('paid', 'in_payment')
      and key('topup:%d' % inv.id).amount == 10000000 and w.ts_available() == before + 10000000, inv.payment_state)
check('T02 credit.topup audited with the move name', Audit.search_count([('event_type', '=', 'credit.topup'), ('detail', 'ilike', inv.name)]) == 1)
inv2 = topup_invoice(2000000, {'ts_billing_no_sync': True})
pay(inv2, {'ts_billing_no_sync': True})
check('T03 (fixture) a payment that skipped the hooks left no row', not key('topup:%d' % inv2.id), inv2.payment_state)
n_sync = Move._cron_sync_topups()
check('T03 the daily sync credits it', key('topup:%d' % inv2.id).amount == 2000000 and n_sync >= 1)
check('T03 a second sync writes nothing', Move._cron_sync_topups() == 0)
refund = inv._reverse_moves([{'invoice_date': fields.Date.today()}])
check('T04 the credit note carries the panel', refund.ts_workspace_id == ws and refund.move_type == 'out_refund')
refund.action_post()
before = w.ts_available()
pay(refund)
check('T04 a paid credit note takes back min(untaxed, top-up)', key('topup-rev:%d' % refund.id).amount == -10000000
      and w.ts_available() == before - 10000000 and key('topup-rev:%d' % refund.id).type == 'adjust', refund.payment_state)
check('T04 credit.topup_reversal audited', Audit.search_count([('event_type', '=', 'credit.topup_reversal'), ('workspace_id', '=', ws.id)]) == 1)
check('T05 accounting records carry no participant data', not env['account.move.line'].search_count(
    [('move_id', 'in', (inv | inv2 | refund).ids), ('name', 'ilike', 'مراجع')]))

# ---------------------------------------------------------------- 9. group invitations
w.ts_adjust(-w.ts_available() + 2 * P1, 'correction')     # leave exactly 2 invitations of credit
Cl = env['ts.panel.client']
clients = Cl.create([{'workspace_id': ws.id, 'name': 'گروهی %d' % k} for k in range(3)])
camp = env['ts.campaign'].create({'workspace_id': ws.id, 'name': 'دعوت گروهی اعتبار', 'instrument_id': i1.id, 'kind': 'list',
                                  'created_by_id': dire.id})
msg = refused(lambda: camp.ts_launch(clients))
check('G01 a batch above the credit is refused once, with the total', msg == INSUFFICIENT % (fmt_toman(2 * P1), fmt_toman(3 * P1)), msg)
check('G01 nothing was created', not A.search_count([('campaign_id', '=', camp.id)]))
c2.ts_set_cap(own, P1)
camp2 = env['ts.campaign'].create({'workspace_id': ws.id, 'name': 'دعوت گروهی سقف', 'instrument_id': i1.id, 'kind': 'list',
                                   'created_by_id': c2.id})
msg = refused(lambda: camp2.ts_launch(clients[:2]))
check('G02 all-or-nothing: the cap stops the 2nd hold and the 1st invitation is undone', msg.startswith('سقف ماهانهٔ شما پر شده است')
      and not A.search_count([('campaign_id', '=', camp2.id)]), msg)
need = 10 * P1
msg = refused(lambda: env['ts.campaign'].create({'workspace_id': ws.id, 'name': 'پیوند باز اعتبار', 'instrument_id': i1.id,
                                                  'kind': 'open_link', 'created_by_id': dire.id, 'open_max': 50}))
check('G03 an open link needs credit for 10 uses', msg == OPEN_LINK_FLOOR % (fmt_toman(need), fa_num(10)), msg)
w.ts_grant(need, 'manual')
ol = env['ts.campaign'].create({'workspace_id': ws.id, 'name': 'پیوند باز اعتبار', 'instrument_id': i1.id, 'kind': 'open_link',
                                'created_by_id': dire.id, 'open_max': 50})
check('G03 with enough credit the open link is created', bool(ol.id))
joined = ol.ts_join(puser('j'), 'پیوسته')
check('G04 a join holds the price', joined.price_held == P1)
w.ts_adjust(-w.ts_available(), 'correction')
nn = N.search_count([('user_id', '=', own.user_id.id), ('type', '=', 'low_balance')])
w.sudo().low_alert_sent_on = False
nc = Cl.search_count([('workspace_id', '=', ws.id)])
pj = puser('j')
msg = refused(lambda: ol.ts_join(pj, 'بی‌اعتبار'))
check('G05 a join without credit: the participant text has no money words', msg == JOIN_FULL and 'اعتبار' not in msg and 'تومان' not in msg, msg)
check('G05 nothing of the join remains (no client, no invitation)', Cl.search_count([('workspace_id', '=', ws.id)]) == nc)
check('G05 the panel gets credit.refused and a low-balance notification',
      Audit.search_count([('event_type', '=', 'credit.refused'), ('workspace_id', '=', ws.id)]) >= 4
      and N.search_count([('user_id', '=', own.user_id.id), ('type', '=', 'low_balance')]) == nn + 1)

# ---------------------------------------------------------------- 10. low balance (threshold, once per 24 h, credits:read only)
w.ts_grant(2 * P1, 'manual')
w.sudo().low_alert_sent_on = False
w.ts_set_threshold(own, 3 * P1)
check('L01 threshold change audited', Audit.search_count([('event_type', '=', 'credit.threshold_change'), ('workspace_id', '=', ws.id)]) == 1)
check('L01 threshold must be a multiple of 10 and set by credits:manage',
      raises(lambda: w.ts_set_threshold(own, 1005), UserError) and raises(lambda: w.ts_set_threshold(c1, 10), UserError))
base_o = N.search_count([('user_id', '=', own.user_id.id), ('type', '=', 'low_balance')])
base_c = N.search_count([('user_id', '=', c1.user_id.id), ('type', '=', 'low_balance')])
al = invite(ws, own, i1, name='کم‌اعتبار')
atl = al.action_accept(puser('p'), share=True)
finish(atl)
row = N.search([('user_id', '=', own.user_id.id), ('type', '=', 'low_balance')], limit=1)
check('L02 after a debit below the threshold the owner is told once, with the panel and the amount',
      N.search_count([('user_id', '=', own.user_id.id), ('type', '=', 'low_balance')]) == base_o + 1
      and ws.name in row.title and 'تومان' in row.title, row.title)
check('L02 a clinician (no credits:read) is not told', N.search_count([('user_id', '=', c1.user_id.id), ('type', '=', 'low_balance')]) == base_c)
check('L03 at most once per 24 h', w._ts_low_balance_notify() is False)

# ---------------------------------------------------------------- 11. free panel unchanged
wf = panel(mode='free')
of, cf = member(wf, 'owner'), member(wf, 'clinician')
af = invite(wf, cf, i1, name='رایگان')
atf = af.action_accept(puser('p'), share=True)
finish(atf)
fr = rows(wf)
check('F01 free panel: no hold, price_held 0, one debit of amount 0', af.price_held == 0 and not key('hold:%d' % af.id)
      and len(fr) == 1 and fr.type == 'debit_usage' and fr.amount == 0 and fr.free)
check('F01 free panel: no money row anywhere', all(r.amount == 0 for r in fr))
check('F02 billing_mode prepaid only by the platform manager', raises(lambda: wf.with_user(of.user_id).write({'billing_mode': 'prepaid'}), Exception))

# ---------------------------------------------------------------- 12. Jalali month boundary of the cap
c3 = member(ws, 'clinician')
w.ts_grant(5 * P1, 'manual')
a3 = invite(ws, c3, i1, name='مرز ماه')
start, _end = jalali_month_bounds()
check('J01 a hold of this month counts', w.ts_month_spend(c3) == P1)
env.flush_all()
env.cr.execute('UPDATE ts_wallet_txn SET txn_date = %s WHERE idem_key = %s', [start - timedelta(seconds=1), 'hold:%d' % a3.id])
env.invalidate_all()
check('J02 one second before the Jalali month starts it does not', w.ts_month_spend(c3) == 0)
env.cr.execute('UPDATE ts_wallet_txn SET txn_date = %s WHERE idem_key = %s', [start, 'hold:%d' % a3.id])
env.invalidate_all()
check('J03 at the first second of the month it does', w.ts_month_spend(c3) == P1)
check('J04 month start is midnight Asia/Tehran (20:30 UTC in summer, 20:30/21:30 UTC)', start.minute == 30 and start.hour in (19, 20), str(start))

# ---------------------------------------------------------------- 13. reconcile after the whole scenario
mine = {ws.id, wf.id}
probs = [p for p in env['ts.wallet']._reconcile() if p[1] in mine]
check('Z01 _reconcile() finds no problem in the test panels', not probs, str(probs[:5]))
check('Z02 ledger rows cannot be edited or deleted', raises(lambda: key('hold:%d' % a3.id).write({'amount': 0}), UserError)
      and raises(lambda: key('hold:%d' % a3.id).unlink(), UserError))

print('SUMMARY %d/%d passed' % (sum(ok for _, ok in results), len(results)))
env.cr.rollback()
