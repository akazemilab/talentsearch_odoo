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
SPECIAL = {'TALENT-INV-15': 250000}
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
        insts = Inst.search([('state', '=', 'published')])
        singles = {}
        for i in insts:
            i._ts_ensure_product()
            p = single_price_toman(i)
            singles[i.id] = p
            if i.product_id.list_price != p * TOMAN:
                i.product_id.list_price = p * TOMAN
        for b in Bat.search([('state', '=', 'published')]):
            b._ts_ensure_product()
            total = sum(singles.get(l.instrument_id.id, 0) for l in b.line_ids)
            p = int(total * 0.7) // 10000 * 10000
            if b.product_id.list_price != p * TOMAN:
                b.product_id.list_price = p * TOMAN
            print('battery %-40s %d instruments, singles %d -> %d toman' % (b.name, len(b.line_ids), total, p))
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
        top_battery = max([b.product_id.list_price for b in Bat.search([('state', '=', 'published')])] or [0])
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
