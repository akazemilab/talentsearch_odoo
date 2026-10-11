# Debug runner (clones only): executes another test file and prints its traceback with FAIL prefixes so `ts test` shows it.
import os, traceback
_target = os.environ.get('TS_DEBUG_FILE') or 'tests_battery.py'
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else '/opt/odoo/talentsearch_stage_s1/tools/prod', _target)).read()
try:
    exec(compile(_src, _target, 'exec'), globals())
except BaseException:
    for _l in traceback.format_exc().splitlines():
        print('FAIL TB ' + _l)
