# Debug runner (clones only): tests_talent.py with its full traceback as FAIL lines.
import os, traceback
assert env.cr.dbname != 'eot_main'
for _d in ('/opt/odoo/talentsearch_stage_s2/tools/prod', '/opt/odoo/talentsearch_stage/tools/prod', '/opt/odoo/talentsearch_stage_s1/tools/prod'):   # odoo shell drops TS_SLOT: slot 2 first (clinic/take work)
    if os.path.exists(os.path.join(_d, 'tests_talent.py')):
        break
try:
    exec(compile(open(os.path.join(_d, 'tests_talent.py')).read(), 'tests_talent.py', 'exec'), globals())
except BaseException:
    for _l in traceback.format_exc().splitlines():
        print('FAIL TB ' + _l)
