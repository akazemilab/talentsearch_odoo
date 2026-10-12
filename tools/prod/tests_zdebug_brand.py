# Debug runner (clones only): BinaryBytes introspection + tests_brand.py traceback with FAIL prefixes.
import os, traceback
assert env.cr.dbname != 'eot_main'
try:
    rec = env['res.partner'].sudo().search([('image_128', '!=', False)], limit=1)
    v = rec.image_128
    print('INFO type %s mro %s' % (type(v), [c.__name__ for c in type(v).__mro__]))
    print('INFO attrs %s' % [a for a in dir(v) if not a.startswith('__')][:40])
    for name, fn in (('bytes', lambda x: bytes(x)[:8]), ('str', lambda x: str(x)[:20]), ('decode', lambda x: x.decode()[:20]),
                     ('content', lambda x: x.content[:8]), ('len', lambda x: len(x))):
        try:
            print('INFO %s -> %r' % (name, fn(v)))
        except Exception as e:
            print('INFO %s !! %r' % (name, e))
except Exception:
    for _l in traceback.format_exc().splitlines():
        print('FAIL TB ' + _l)
for _d in ('/opt/odoo/talentsearch_stage/tools/prod', '/opt/odoo/talentsearch_stage_s1/tools/prod'):
    if os.path.exists(os.path.join(_d, 'tests_brand.py')):
        break
_src = open(os.path.join(_d, 'tests_brand.py')).read()
try:
    exec(compile(_src, 'tests_brand.py', 'exec'), globals())
except BaseException:
    for _l in traceback.format_exc().splitlines():
        print('FAIL TB ' + _l)
