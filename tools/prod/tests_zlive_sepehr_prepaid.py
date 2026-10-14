# LIVE one-off (owner 2026-10-12 07:18 Tehran: "set a price based on the Iran market for B2B inside a clinic, switch to
# prepaid, and add a 10 million toman top-up"). Runs through `ts test eot_main tests_zlive_sepehr_prepaid.py` (slot 0).
#
# Price basis (B2B, per completed use, self-administered inventory with automatic scoring and report): 1405 counseling
# session tariffs are reported at 750,000-2,000,000 toman per 45 minutes; one inventory used inside a counseling session
# is priced at about 10-25% of a session, by length:
#   up to 30 statements: 80,000 toman · 31-60: 120,000 · over 60: 180,000 · TALENT-INV-15 (interactive): 250,000
#   battery = 70% of the sum of its single prices, rounded down to 10,000 toman.
# The top-up is posted as a back-office grant (reason promo, «اعتبار شروع»): no money was received, so no invoice or
# payment is recorded (a real bank transfer later goes through «صدور فاکتور اعتبار» + register payment).
# Idempotent: prices are set to the same values; the mode switch is a no-op the second time; the grant uses a fixed key.
import io, contextlib, traceback

assert env.cr.dbname == 'eot_main', 'this file is only for the live database'
su = env(su=True)
TOMAN = 10
TIERS = ((30, 80000), (60, 120000), (10 ** 6, 180000))
SPECIAL = {'TALENT-INV-15': 1500000}        # owner 2026-10-14 12:12: «۱.۵ میلیون تومن» (was 250,000)
# owner 2026-10-14 12:12: the intake battery «ارزیابی آغاز مشاوره» costs 800,000 toman and the other batteries keep their
# ratio to it (was 300,000 = 70% of its parts): new = old x 800/300, rounded to the nearest 10,000 toman.
BATTERY_TOMAN = {'BAT-INTAKE-1': 800000, 'BAT-DISTRESS-1': 670000, 'BAT-WORK-1': 670000, 'BAT-LIFE-1': 590000,
                 'BAT-COUPLE-1': 590000, 'BAT-CHILD-1': 430000}
GRANT_RIAL = 10000000 * TOMAN
GRANT_KEY = 'grant:sepehr-start-1405-07-20'


def single_price_toman(inst):
    if inst.code in SPECIAL:
        return SPECIAL[inst.code]
    n = len(inst.current_version_id.item_ids.filtered(lambda i: not i.disabled))
    return next(p for limit, p in TIERS if n <= limit)


out = io.StringIO()
try:
    with contextlib.redirect_stdout(out):
        Inst = su['ts.instrument']
        Bat = su['ts.battery']
        # clinic/school catalog only: hiring (purpose employment) and the free career tests are priced elsewhere, if ever
        # (2026-10-14: a run over every published instrument priced them by mistake; tests_zlive_restore_hr_prices.py)
        insts = Inst.search([('state', '=', 'published'), ('purpose', '!=', 'employment'), ('code', 'not like', 'CAREER-%')])
        singles = {}
        for i in insts:
            i._ts_ensure_product()
            p = single_price_toman(i)
            singles[i.id] = p
            if i.product_id.list_price != p * TOMAN:
                i.product_id.list_price = p * TOMAN
        for b in Bat.search([('state', '=', 'published'), ('code', 'in', list(BATTERY_TOMAN))]):
            b._ts_ensure_product()
            total = sum(singles.get(l.instrument_id.id, 0) for l in b.line_ids)
            p = BATTERY_TOMAN.get(b.code, int(total * 0.7) // 10000 * 10000)   # explicit owner prices first
            if b.product_id.list_price != p * TOMAN:
                b.product_id.list_price = p * TOMAN
            print('battery %-16s %d instruments, singles %d -> %d toman' % (b.code, len(b.line_ids), total, p))
        by_tier = {}
        for i in insts:
            by_tier[singles[i.id]] = by_tier.get(singles[i.id], 0) + 1
        print('singles by price (toman: count): %s' % dict(sorted(by_tier.items())))

        ws = su['ts.workspace'].search([('name', '=', 'سپهر هیجان اندیش')], limit=1)
        assert ws, 'Sepehr workspace not found'
        if ws.billing_mode != 'prepaid':
            ws.billing_mode = 'prepaid'
        w = su['ts.wallet']._for_workspace(ws)
        Txn = su['ts.wallet.txn']
        if not Txn.search_count([('idem_key', '=', GRANT_KEY)]):
            w._post('grant', GRANT_RIAL, 0, GRANT_KEY, 'promo', free=False)
            su['ts.audit.event'].log('wallet.grant', w, workspace=ws, amount=GRANT_RIAL, reason='promo')
        top_battery = max([b.product_id.list_price for b in Bat.search([('code', 'in', list(BATTERY_TOMAN))])] or [0])
        threshold = int(top_battery * 3)
        if w.low_threshold != threshold:
            w.low_threshold = threshold
        env.cr.commit()
        print('Sepehr mode=%s available=%d toman held=%d threshold=%d toman' % (
            ws.billing_mode, w.ts_available() // TOMAN, w.ts_held() // TOMAN, threshold // TOMAN))
        print('Sepehr granted items priced: %d instruments, %d batteries' % (
            len(ws.catalog_instrument_ids), len(ws.catalog_battery_ids)))
except BaseException:
    env.cr.rollback()
    for line in traceback.format_exc().splitlines():
        print('FAIL TB ' + line)
for line in out.getvalue().splitlines():
    print('SUMMARY ' + line)
