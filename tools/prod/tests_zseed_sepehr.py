# Clone-only wrapper so `ts test` can run the Sepehr seed and show its lines (prefixed SUMMARY) and any traceback (FAIL).
import io, os, contextlib, traceback
_base = '/opt/odoo/talentsearch_stage%s/tools/prod' % ('' if os.environ.get('TS_SLOT', '1') == '0' else '_s1')
assert env.cr.dbname.startswith('eot_ts'), 'clones only'
_buf = io.StringIO()
try:
    with contextlib.redirect_stdout(_buf):
        exec(compile(open(os.path.join(_base, 'clinic_seed_sepehr.py')).read(), 'clinic_seed_sepehr.py', 'exec'), globals())
except BaseException:
    for _l in traceback.format_exc().splitlines():
        print('FAIL TB ' + _l)
for _l in _buf.getvalue().splitlines():
    print('SUMMARY ' + _l)
