# LIVE one-off (owner approval 2026-10-11 20:41 Tehran: "Use mine now: 09125930846. Go"): create the counseling-center
# panel «سپهر هیجان اندیش» on eot_main with the owner's own portal account as panel owner. No invitations, no SMS
# (owner: "don't send anything from here"). Runs through `ts test eot_main tests_zseed_sepehr_live.py` from slot 0.
# Refuses any database other than eot_main. Idempotent (clinic_seed_sepehr.py upserts).
import io, os, contextlib, traceback
assert env.cr.dbname == 'eot_main', 'this file is only for the live database'
os.environ['TS_ALLOW_LIVE'] = '1'
os.environ['TS_SEPEHR_OWNER_LOGIN'] = '09125930846'   # the owner's own mobile sign-in (portal user)
os.environ.pop('TS_SEPEHR_INVITES', None)
_base = '/opt/odoo/talentsearch_stage/tools/prod'
_buf = io.StringIO()
try:
    with contextlib.redirect_stdout(_buf):
        exec(compile(open(os.path.join(_base, 'clinic_seed_sepehr.py')).read(), 'clinic_seed_sepehr.py', 'exec'), globals())
except BaseException:
    for _l in traceback.format_exc().splitlines():
        print('FAIL TB ' + _l)
for _l in _buf.getvalue().splitlines():
    print('SUMMARY ' + _l)
