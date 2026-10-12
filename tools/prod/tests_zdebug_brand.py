# Debug runner (clones only): tests_brand.py with its full traceback as FAIL lines.
import os, traceback
assert env.cr.dbname != 'eot_main'
for _d in ('/opt/odoo/talentsearch_stage/tools/prod', '/opt/odoo/talentsearch_stage_s1/tools/prod', '/opt/odoo/talentsearch_stage_s2/tools/prod'):
    if os.path.exists(os.path.join(_d, 'tests_brand.py')):
        break
try:
    exec(compile(open(os.path.join(_d, 'tests_brand.py')).read(), 'tests_brand.py', 'exec'), globals())
except BaseException:
    for _l in traceback.format_exc().splitlines():
        print('FAIL TB ' + _l)
