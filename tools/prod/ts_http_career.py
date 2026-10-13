#!/usr/bin/env python3
"""Free career match over HTTP against a served CLONE:  ts_http_career.py DB PORT

A signed-in person opens /career, starts (one run, the interest module), consents once, answers the 60 interests
(investigative and social high), submits, lands on the two background questions, sees the QUICK list (an
investigative/social job near the top, levels and readiness), opens one job page (four panels), starts the work-style
module (no second consent), answers it, and the list turns FULL. The daily cap closes the start for a new person.
The interest and work-style modules are not in the public catalog."""
import importlib.util
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
L = {'p': 'ts.career.http@example.invalid', 'q': 'ts.career.http2@example.invalid'}
pw = {u: ensure_user(u) for u in L.values()}

out = shell(r"""
L = %r
for lg in L.values():
    u = env['res.users'].search([('login', '=', lg)])
    env['ts.career.run'].sudo().search([('user_id', '=', u.id)]).unlink()
env['ir.config_parameter'].sudo().set_str('ts_career.daily_cap', '1000')
ip = env['ts.instrument'].sudo().search([('code', '=', 'CAREER-IP-60')])
hx = env['ts.instrument'].sudo().search([('code', '=', 'CAREER-HEXACO-1')])
env.cr.commit()
print('ITEMS', ' '.join('%%d:%%s' %% (i.id, i.factor_id.code) for i in ip.current_version_id.item_ids))
print('HEX', ' '.join('%%d:%%s' %% (i.id, i.factor_id.code) for i in hx.current_version_id.item_ids if not i.disabled))
print('STATE', ip.state, hx.state)
""" % L)
m = re.search(r'ITEMS (.*)', out)
assert m, out[-1500:]
items = [tuple(x.split(':')) for x in m.group(1).split()]
hexi = [tuple(x.split(':', 1)) for x in re.search(r'HEX (.*)', out).group(1).split()]
check('both modules published', 'STATE published published' in out, out[-300:])
check('60 interest items', len(items) == 60, str(len(items)))


p = Client(TS)
assert p.login(L['p'], pw[L['p']])
st, loc, body = p.req('/career')
check('start page', st == 200 and 'tsc-start' in body and 'رایگان' in body, str(st))
st, loc, body = p.req('/career/start')
check('start -> player', st in (302, 303) and '/take/' in loc, loc)
T = path_of(loc).split('/take/')[1].split('?')[0]
st, loc, body = p.req('/take/%s' % T)
check('consent page once', st == 200 and 'consent_service' in body, str(st))
st, loc, _ = p.req('/take/%s/consent' % T, [('consent_service', '1'), ('age18', 'yes'), ('csrf_token', p.csrf(body))])
st, loc, body = p.req('/take/%s' % T)
check('interest prompt on the player', 'چقدر دوست دارید این کار را انجام دهید' in body, str(st))
check('no "about you" prompt for interests', 'چقدر دربارهٔ شما درست است' not in body)
val = {'R': 2, 'I': 5, 'A': 1, 'S': 4, 'E': 1, 'C': 2}
data = [('page', '1'), ('go', 'review')] + [('q_%s' % i, str(val[f])) for i, f in items] + [('csrf_token', p.csrf(body))]
p.req('/take/%s/page' % T, data)
_, _, body = p.req('/take/%s/review' % T)
st, loc, _ = p.req('/take/%s/submit' % T, [('csrf_token', p.csrf(body))])
check('submit -> report -> career', st in (302, 303), loc)
st, loc, _ = p.req(path_of(loc))
check('report redirects to /career/r', st in (302, 303) and path_of(loc) == '/career/r', loc)
st, loc, body = p.req('/career/r')
check('background questions first', st == 200 and 'tsc-bg' in body and 'name="edu"' in body, str(st))
st, loc, _ = p.req('/career/r', [('edu', '4'), ('exp', '1_2'), ('csrf_token', p.csrf(body))])
check('background saved', st in (302, 303) and path_of(loc) == '/career/r', loc)
st, loc, body = p.req('/career/r')
check('quick result list', st == 200 and 'tsc-jobs' in body and 'شغل‌هایی که با علایق شما هم‌خوان‌اند' in body, str(st))
check('profile shows investigative first', body.find('جست‌وجوگر') != -1 and body.find('جست‌وجوگر') < body.find('هنری'))
check('levels and readiness shown', 'tsc-pill--' in body and ('آماده' in body or 'فاصله' in body))
check('beta and not-for-hiring line', 'نسخهٔ آزمایشی' in body and 'نه تصمیم استخدام' in body)
codes = re.findall(r'href="/career/job/([0-9.\-]+)"', body)
check('20 jobs listed', len(codes) == 20, str(len(codes)))
st, loc, jb = p.req('/career/job/%s' % codes[0])
check('job page four panels', st == 200 and all(h in jb for h in ('تناسب', 'آمادگی', 'دلایل و عدم‌قطعیت')), str(st))
st, loc, body2 = p.req('/career/r?ready=1')
check('ready filter', st == 200 and 'aria-current="page"' in body2, str(st))
st, loc, body3 = p.req('/career/r?n=40')
check('20 more', len(re.findall(r'href="/career/job/', body3)) == 40)
st, loc, _ = p.req('/career/more/personality', [('csrf_token', p.csrf(body))])
check('personality -> player', st in (302, 303) and '/take/' in loc, loc)
T2 = path_of(loc).split('/take/')[1].split('?')[0]
st, loc, b2 = p.req('/take/%s' % T2)
check('no second consent', st == 200 and 'consent_service' not in b2 and 'ts-qform' in b2, str(st))
facets_hi = {'Inquisitiveness', 'Diligence', 'Organization', 'Sentimentality', 'Perfectionism'}
hv = [('q_%s' % i, '5' if f in facets_hi else ('3' if f != 'ATTN' else '1')) for i, f in hexi]
p.req('/take/%s/page' % T2, [('page', '1'), ('go', 'review')] + hv + [('csrf_token', p.csrf(b2))])
_, _, b2 = p.req('/take/%s/review' % T2)
st, loc, _ = p.req('/take/%s/submit' % T2, [('csrf_token', p.csrf(b2))])
st, loc, _ = p.req(path_of(loc))
check('personality report -> career', path_of(loc) == '/career/r', loc)
st, loc, body = p.req('/career/r')
check('full list after personality', st == 200 and 'با علایق و سبک کاری شما' in body and 'tsc-go-personality' not in body, str(st))
st, loc, body = p.req('/assessments?all=1')
check('career modules not in public catalog', 'CAREER-IP-60' not in body and 'علایق شغلی' not in body, str(st))

shell(r"""
env['ir.config_parameter'].sudo().set_str('ts_career.daily_cap', '0')
env.cr.commit()
""")
q = Client(TS)
assert q.login(L['q'], pw[L['q']])
st, loc, body = q.req('/career')
check('cap reached: no start button', st == 200 and 'tsc-full' in body and 'tsc-start' not in body, str(st))
st, loc, _ = q.req('/career/start')
check('cap reached: start refused', path_of(loc) == '/career', loc)
st, loc, body = p.req('/career/r')
check('existing run still opens', st == 200 and 'tsc-jobs' in body, str(st))
shell(r"""
env['ir.config_parameter'].sudo().set_str('ts_career.daily_cap', '100')
env.cr.commit()
""")
anon = Client(TS)
st, loc, body = anon.req('/career')
check('public start page', st == 200 and 'tsc-start' in body and 'با شمارهٔ همراه وارد' in body, str(st))
st, loc, _ = anon.req('/career/start')
check('public start -> signup', '/signup' in loc and 'career' in loc, loc)
summary()
