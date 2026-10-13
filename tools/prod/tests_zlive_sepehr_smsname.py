# LIVE one-off (owner 2026-10-13: «decide about others too»): Sepehr's SMS short name = «سپهر هیجان اندیش» (16 ≤ 18).
# Idempotent: sets it only when empty. Run: `ts test eot_main tests_zlive_sepehr_smsname.py` (slot 0).
import io, contextlib, traceback
assert env.cr.dbname == 'eot_main', 'this file is only for the live database'
out = io.StringIO()
try:
    with contextlib.redirect_stdout(out):
        ws = env(su=True)['ts.workspace'].search([('name', '=', 'سپهر هیجان اندیش')], limit=1)
        assert ws, 'Sepehr workspace not found'
        if not (ws.sms_name or '').strip():
            ws.sms_name = 'سپهر هیجان اندیش'
            env.cr.commit()
        print('Sepehr sms_name=%s sender=%s' % (ws.sms_name, ws.ts_sms_sender()))
except BaseException:
    env.cr.rollback()
    for line in traceback.format_exc().splitlines():
        print('FAIL TB ' + line)
for line in out.getvalue().splitlines():
    print('SUMMARY ' + line)
