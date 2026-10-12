# LIVE, read-only: what the Sepehr owner sees in «راه‌اندازی مرکز» and the panel's state. Writes nothing (rollback at end).
assert env.cr.dbname == 'eot_main'
try:
    su = env(su=True)
    ws = su['ts.workspace'].search([('name', '=', 'سپهر هیجان اندیش')], limit=1)
    print('SUMMARY ws id=%s state=%s purpose=%s billing=%s brand=%s' % (ws.id, ws.state, ws.purpose, ws.billing_mode, ws.ts_brand_enabled()))
    print('SUMMARY identity public_name=%r sms_name=%r has_logo=%s' % (ws.public_name, ws.sms_name, ws.ts_has_logo()))
    for m in ws.member_ids.filtered('active'):
        print('SUMMARY member id=%s role=%s applies=%s' % (m.id, m.role, m.ts_onb_applies()))
        ck = m.ts_onb_checklist()
        if not ck:
            print('SUMMARY   checklist: none'); continue
        print('SUMMARY   checklist %s of %s done' % (ck['done_n'], ck['total']))
        for s in ck['steps']:
            print('SUMMARY   - %-10s done=%-5s current=%-5s url=%s note=%s' % (s['key'], s['done'], s.get('current'), s.get('url'), s.get('note')))
        for st in ck['status']:
            print('SUMMARY   status %s ok=%s %s' % (st.get('key'), st.get('ok'), st.get('value')))
    w = su['ts.wallet']._for_workspace(ws)
    print('SUMMARY wallet available=%s toman' % (w.ts_available() // 10))
except Exception:
    import traceback
    for l in traceback.format_exc().splitlines():
        print('FAIL TB ' + l)
finally:
    env.cr.rollback()
