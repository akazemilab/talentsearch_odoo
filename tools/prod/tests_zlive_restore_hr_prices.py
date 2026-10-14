# LIVE one-off (2026-10-14 ~08:45 UTC): undo the prices that tests_zlive_sepehr_prepaid.py gave to items outside the
# clinic catalog when it still ran over every published record. These products were created after 2026-10-12 with the
# default price 0 (ts_billing _product_vals) and had never been priced; hiring prices are an open owner decision.
# Runs through `ts test eot_main tests_zlive_restore_hr_prices.py` (slot 0). Idempotent.
assert env.cr.dbname == 'eot_main', 'live only'
su = env(su=True)
INST = ['HR-HEXACO-1', 'TASK-NUMERIC', 'TASK-REASON', 'TASK-SPATIAL', 'TASK-SPEED', 'TASK-VERIFY', 'CAREER-HEXACO-1', 'CAREER-IP-60']
BAT = ['BAT-HR-SHORT', 'BAT-HR-FULL']
try:
    recs = list(su['ts.instrument'].search([('code', 'in', INST)])) + list(su['ts.battery'].search([('code', 'in', BAT)]))
    for r in recs:
        old = r.product_id.list_price if r.product_id else 0
        if r.product_id and old:
            r.product_id.list_price = 0
        print('SUMMARY %-16s %d -> 0 toman' % (r.code, old // 10))
    env.cr.commit()
    print('SUMMARY restored %d of %d' % (len(recs), len(INST) + len(BAT)))
except Exception:
    import traceback
    env.cr.rollback()
    for l in traceback.format_exc().splitlines():
        print('FAIL TB ' + l)
