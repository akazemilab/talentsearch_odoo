# LIVE one-off (owner 2026-10-14 «add talent inventory too»): put TALENT-INV-15 (the interactive talent inventory,
# 250,000 toman per use, price set by tests_zlive_sepehr_prepaid.py) into the Sepehr panel's granted catalog so the office
# can send it and «خدمات» lists it. Verified on clone eot_ts703 (ts_http_clin8 H01, H09, H16, H17): sent by the office,
# the therapist reads it at the counselor level, the office sees the status only.
# Runs through `ts test eot_main tests_zlive_sepehr_talent.py` (slot 0). Idempotent.
assert env.cr.dbname == 'eot_main', 'live only'
su = env(su=True)
try:
    ws = su['ts.workspace'].browse(4)
    assert ws.name == 'سپهر هیجان اندیش' and ws.purpose == 'clinical' and ws.catalog_mode == 'granted'
    talent = su['ts.instrument'].search([('code', '=', 'TALENT-INV-15'), ('state', '=', 'published')], limit=1)
    assert talent and talent.product_id and talent.product_id.list_price > 0, 'talent inventory missing or unpriced'
    if talent in ws.catalog_instrument_ids:
        print('SUMMARY talent inventory already in the Sepehr catalog')
    else:
        ws.write({'catalog_instrument_ids': [(4, talent.id)]})
        env.cr.commit()
        print('SUMMARY talent inventory added to the Sepehr catalog (%d instruments now)' % len(ws.catalog_instrument_ids))
    print('SUMMARY price %d toman, offered to members: %s' % (
        talent.product_id.list_price // 10,
        ', '.join('%s:%s' % (m.role, talent in m.allowed_instruments()) for m in ws.member_ids.filtered('active'))))
except Exception:
    import traceback
    env.cr.rollback()
    for l in traceback.format_exc().splitlines():
        print('FAIL TB ' + l)
