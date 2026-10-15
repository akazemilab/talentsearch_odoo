#!/usr/bin/env python3
"""Free career match over HTTP against a served CLONE:  ts_http_career.py DB PORT

Signed in: /career offers the one-tap start (reminder box ticked, research box not); the tap opens the interests with no
consent page; 30 items a page in card mode with the journey and the end card («نیمی از راه»); the last page ends straight
in the result (no review screen); the two background questions; the QUICK list (an investigative/social job near the top,
levels and readiness), the three levels, the reminder switch; one job page; reminders queue (l2_invite, l2_stall) and their
SMS text carries /career/c/<code>; the SMS link opens the right step for the owner only; work styles in four sittings
(«بعداً ادامه می‌دهم» -> /career/r?paused=1), then the list turns FULL. Funnel steps are counted. The daily cap closes
the start for a new person.
Guest (completion phase B): /career/go starts the interests without an account (guest player, cookie), «بعداً» goes back to
/career with a continue button, the last page goes to the result gate with the career wording, and the claim after
sign-in makes the run (reminders as ticked) and opens the two questions."""
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
Client, check, ensure_user, summary, shell, path_of, follow = (lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell,
                                                              lib.path_of, lib.follow)
TS = 'talentsearch.ir'
L = {'p': 'ts.career.http@example.invalid', 'q': 'ts.career.http2@example.invalid', 'g': 'ts.career.http3@example.invalid'}
pw = {u: ensure_user(u) for u in L.values()}

out = shell(r"""
L = %r
for lg in L.values():
    u = env['res.users'].search([('login', '=', lg)])
    env['ts.career.run'].sudo().search([('user_id', '=', u.id)]).unlink()
env['ir.config_parameter'].sudo().set_str('ts_career.daily_cap', '1000')
env['ts.rate.hit'].sudo().search([('key', '=like', 'guest:%%')]).unlink()
ip = env['ts.instrument'].sudo().search([('code', '=', 'CAREER-IP-60')])
hx = env['ts.instrument'].sudo().search([('code', '=', 'CAREER-HEXACO-1')])
env.cr.commit()
print('ITEMS', ' '.join('%%d:%%s' %% (i.id, i.factor_id.code) for i in ip.current_version_id.item_ids))
print('HEX', '|'.join('%%d:%%s' %% (i.id, i.factor_id.code) for i in hx.current_version_id.item_ids if not i.disabled))
print('STATE', ip.state, hx.state, ip.ts_page_size(), ip.ts_card_mode(), hx.ts_page_size())
""" % L)
m = re.search(r'ITEMS (.*)', out)
assert m, out[-1500:]
items = [tuple(x.split(':')) for x in m.group(1).split()]
hexi = [tuple(x.split(':', 1)) for x in re.search(r'HEX (.*)', out).group(1).split('|')]
check('both modules published, 30 a page, card mode', 'STATE published published 30 True 30' in out, out[-300:])
check('60 interest items', len(items) == 60, str(len(items)))
val = {'R': 2, 'I': 5, 'A': 1, 'S': 4, 'E': 1, 'C': 2}


def run_info(login):
    return shell(r"""
u = env['res.users'].search([('login', '=', %r)])
r = env['ts.career.run'].sudo().search([('user_id', '=', u.id)])
print('RUN', len(r), r.remind if r else None, bool(r.edu) if r else None, r.ts_state()['ip_done'] if r else None, r.short_code or '-' if r else '-')
""" % login)


# ======================================================================== signed in
p = Client(TS)
assert p.login(L['p'], pw[L['p']])
st, loc, body = p.req('/career')
check('start page: one-tap form, reminder ticked, research not', st == 200 and 'id="tsc-start-form"' in body
      and re.search(r'name="remind" value="1" checked', body) and 'name="consent_research" value="1"/>' in body
      and '۱۸ سال یا بیشتر دارم؛ شروع آزمون' in body, str(st))
st, loc, _ = p.req('/career/go', [('csrf_token', p.csrf(body)), ('remind', '1')])
check('one tap -> the interests', st in (302, 303) and '/take/' in loc, loc)
T = path_of(loc).split('/take/')[1].split('?')[0]
st, loc, body = p.req('/take/%s' % T)
check('no consent page after the tap', st == 200 and 'consent_service' not in body and 'ts-qform' in body, str(st))
check('card mode, 30 items on the first page', 'data-card="1"' in body and body.count('class="ts-q"') == 30, str(body.count('class="ts-q"')))
check('journey and the half-way end card', 'tsc-journey' in body and 'id="ts-cardend"' in body and 'نیمی از راه را آمده‌اید' in body
      and 'id="tsc-later"' in body)
check('interest prompt on the player', 'چقدر دوست دارید این کار را انجام دهید' in body)
st, loc, _ = p.req('/take/%s/page' % T, [('page', '1'), ('go', 'next')] + [('q_%s' % i, str(val[f])) for i, f in items[:30]]
                   + [('csrf_token', p.csrf(body))])
check('page 1 -> page 2', st in (302, 303) and 'page=2' in loc, loc)
st, loc, body = p.req(path_of(loc))
check('page 2: the last 30 and «دیدن نتیجه»', st == 200 and body.count('class="ts-q"') == 30 and 'id="tsc-finish"' in body, str(st))
st, loc, _ = p.req('/take/%s/page' % T, [('page', '2'), ('go', 'review')] + [('q_%s' % i, str(val[f])) for i, f in items[30:]]
                   + [('csrf_token', p.csrf(body))])
check('the last page ends straight in the result (no review screen)', st in (302, 303) and '/my/assessments/' in loc, loc)
st, loc, _ = p.req(path_of(loc))
check('report redirects to /career/r', st in (302, 303) and path_of(loc) == '/career/r', loc)
st, loc, body = p.req('/career/r')
check('background questions with the journey', st == 200 and 'tsc-bg' in body and 'name="edu"' in body and 'tsc-journey' in body, str(st))
st, loc, _ = p.req('/career/r', [('edu', '4'), ('exp', '1_2'), ('csrf_token', p.csrf(body))])
check('background saved', st in (302, 303) and path_of(loc) == '/career/r', loc)
st, loc, body = p.req('/career/r')
check('quick result: a short list', st == 200 and 'tsc-jobs' in body and 'شغلی که بیشترین هم‌خوانی را با شما دارند' in body and 'بر پایهٔ علایق شما' in body, str(st))
names = re.findall(r'class="tsc-bars__name">([^<]+)<', body)
check('profile shows investigative first, then social', names[:2] == ['جست‌وجوگر', 'اجتماعی'], str(names))
check('levels and readiness shown', 'tsc-pill--' in body and ('آماده' in body or 'فاصله' in body))
check('three levels, level 2 current, reminder switch on', 'tsc-levels' in body and 'tsc-go-personality' in body
      and 'بعد از بخش ۲ باز می‌شود' in body and 'id="tsc-remind-off"' in body)
check('beta and not-for-hiring line', 'نسخهٔ آزمایشی' in body and 'تصمیم استخدام' in body)
codes = re.findall(r'href="/career/job/([0-9.\-]+)"', body)
check('5 to 10 jobs, grouped by area', 5 <= len(codes) <= 10 and 'tsc-area__h' in body, str(len(codes)))
_, _, ball = p.req('/career/r?all=1')
check('full list behind a link: 20 jobs', 'tsc-all' in body and len(re.findall(r'href="/career/job/', ball)) == 20)
st, loc, jb = p.req('/career/job/%s' % codes[0])
check('job page four panels', st == 200 and all(h in jb for h in ('تناسب', 'آمادگی', 'دلایل و عدم‌قطعیت')), str(st))

# reminders: off and on again
st, loc, _ = p.req('/career/remind', [('csrf_token', p.csrf(body)), ('on', '0'), ('back', '/career/r')])
check('reminders off', st in (302, 303) and path_of(loc) == '/career/r' and 'RUN 1 False' in run_info(L['p']), loc)
_, _, body = p.req('/career/r')
check('switch now offers «روشن کردن»', 'id="tsc-remind-on"' in body)
p.req('/career/remind', [('csrf_token', p.csrf(body)), ('on', '1'), ('back', '/career/r')])
info = run_info(L['p'])
check('reminders on again', 'RUN 1 True True True' in info, info.strip()[-80:])

# the hourly run: the list was seen 4 days ago and work styles never started -> l2_invite (no SMS from a clone)
out = shell(r"""
from datetime import timedelta
from odoo import fields
u = env['res.users'].search([('login', '=', %r)])
r = env['ts.career.run'].sudo().search([('user_id', '=', u.id)])
r.write({'computed_at': fields.Datetime.now() - timedelta(days=4), 'first_result_at': fields.Datetime.now() - timedelta(days=4)})
N = env['ts.career.nudge'].sudo()
N._ts_run()
row = N.search([('run_id', '=', r.id), ('kind', '=', 'l2_invite')])
print('NUDGE', len(row), row.state, row.reason or '-')
print('BODY', row._ts_body().replace('\n', ' | '))
print('CODE', r.ts_short_code())
N._ts_run()
print('ONCE', N.search_count([('run_id', '=', r.id), ('kind', '=', 'l2_invite')]))
env.cr.commit()
""" % L['p'])
check('l2_invite queued once and never sent from a clone', re.search(r'NUDGE 1 (skipped|queued) ', out) and 'ONCE 1' in out, out.strip()[-200:])
check('reminder text: brand first, no test named, the short link last', re.search(r'BODY استعدادیاب \| .* \| \S+/career/c/[a-z0-9]{12}$', out, re.M)
      and 'شغل' not in re.search(r'BODY (.*)', out).group(1), out.strip()[-200:])
CODE = re.search(r'CODE ([a-z0-9]+)', out).group(1)
st, loc, _ = p.req('/career/c/%s' % CODE)
check('SMS link opens the list for its owner', st in (302, 303) and path_of(loc) == '/career/r', loc)
st, loc, _ = Client(TS).req('/career/c/%s' % CODE)
check('SMS link asks a visitor to sign in first', st in (302, 303) and '/signup' in loc and CODE in loc, loc)
st, loc, _ = Client(TS).req('/career/c/zzzzzzzzzzzz')
check('unknown code -> /career', st in (302, 303) and path_of(loc) == '/career', loc)

# work styles: four sittings, «بعداً» goes back with the paused note, then all of it
st, loc, _ = p.req('/career/more/personality', [('csrf_token', p.csrf(body))])
check('personality -> player', st in (302, 303) and '/take/' in loc, loc)
T2 = path_of(loc).split('/take/')[1].split('?')[0]
st, loc, b2 = p.req('/take/%s' % T2)
check('no second consent, card mode, 30 a sitting, «جای خوبی برای مکث»', st == 200 and 'consent_service' not in b2 and 'ts-qform' in b2
      and 'data-card="1"' in b2 and b2.count('class="ts-q"') == 30 and 'جای خوبی برای مکث است' in b2, str(st))
facets_hi = {'Inquisitiveness', 'Diligence', 'Organization', 'Sentimentality', 'Perfectionism'}
hv = [('q_%s' % i, '5' if f in facets_hi else ('3' if f != 'ATTN' else '1')) for i, f in hexi]
st, loc, _ = p.req('/take/%s/page' % T2, [('page', '1'), ('go', 'exit')] + hv[:30] + [('csrf_token', p.csrf(b2))])
check('«بعداً ادامه می‌دهم» -> /career/r?paused=1', st in (302, 303) and path_of(loc) == '/career/r?paused=1', loc)
st, loc, body = p.req('/career/r?paused=1')
check('paused note promises a reminder, level 2 continues', 'id="tsc-paused"' in body and 'ادامهٔ سبک‌های کاری' in body and 'دقیقه مانده' in body)
out = shell(r"""
from datetime import timedelta
u = env['res.users'].search([('login', '=', %r)])
r = env['ts.career.run'].sudo().search([('user_id', '=', u.id)])
hx = r.ts_attempt('CAREER-HEXACO-1')
env.flush_all()
env.cr.execute("update ts_attempt_answer set write_date = now() - interval '25 hours' where attempt_id = %%s", [hx.id])
env.invalidate_all()
env['ts.career.nudge'].sudo()._ts_run()
print('L2S', env['ts.career.nudge'].sudo().search_count([('run_id', '=', r.id), ('kind', '=', 'l2_stall')]))
env.cr.commit()
""" % L['p'])
check('work styles idle 24 h -> l2_stall queued', 'L2S 1' in out, out.strip()[-200:])
p.req('/take/%s/page' % T2, [('page', '1'), ('go', 'review')] + hv + [('csrf_token', p.csrf(b2))])
st, loc, body = p.req('/career/r')
check('full list after personality', st == 200 and 'بر پایهٔ علایق و سبک کاری' in body and 'tsc-go-personality' not in body
      and 'tsc-go-abilities' in body, str(st))
st, loc, body = p.req('/assessments?all=1')
check('career modules not in public catalog', 'CAREER-IP-60' not in body and 'علایق شغلی' not in body, str(st))
out = shell(r"""
F = env['ts.funnel.event'].sudo()
ip = env['ts.instrument'].sudo().search([('code', '=', 'CAREER-IP-60')])
print('FUN', ' '.join('%s=%d' % (s, F.search_count([('step', '=', s), ('instrument_id', '=', ip.id)]))
                      for s in ('career_view', 'career_start', 'q1', 'half', 'finish', 'bg_done', 'result_view', 'remind_off')))
print('NB', F.search_count([('step', '=', 'nudge_back')]))
""")
fm = dict(re.findall(r'(\w+)=(\d+)', out.split('FUN', 1)[-1].split('\n')[0]))
check('funnel: every career step counted', len(fm) == 8 and all(int(v) > 0 for v in fm.values()), out.strip()[-300:])

# ======================================================================== the daily cap
shell(r"""
env['ir.config_parameter'].sudo().set_str('ts_career.daily_cap', '0')
env.cr.commit()
""")
q = Client(TS)
assert q.login(L['q'], pw[L['q']])
st, loc, body = q.req('/career')
check('cap reached: no start form', st == 200 and 'tsc-full' in body and 'tsc-start-form' not in body, str(st))
st, loc, _ = q.req('/career/start')
check('cap reached: start refused', path_of(loc) == '/career', loc)
st, loc, _ = q.req('/take/%s' % T)
check("another person's interest module is not reachable", st in (403, 404), str(st))
st, loc, _ = q.req('/career/c/%s' % CODE)
check("another person's SMS link opens nothing of theirs", st in (302, 303) and path_of(loc) == '/career', loc)
st, loc, body = p.req('/career/r')
check('existing run still opens', st == 200 and 'tsc-jobs' in body, str(st))
shell(r"""
env['ir.config_parameter'].sudo().set_str('ts_career.daily_cap', '100')
env.cr.commit()
""")

# ======================================================================== guest (phase B)
g = Client(TS)
st, loc, body = g.req('/career')
check('public start page: start without signing up', st == 200 and 'id="tsc-start-form"' in body and 'بدون ثبت‌نام شروع کنید' in body, str(st))
st, loc, _ = g.req('/career/start')
check('old start link -> /career (no sign-in wall)', st in (302, 303) and path_of(loc) == '/career', loc)
st, loc, _ = g.req('/career/go', [('csrf_token', g.csrf(body)), ('remind', '1')])
check('a visitor taps start -> guest interests', st in (302, 303) and path_of(loc) == '/start/q', loc)
st, loc, body = g.req('/start/q')
check('guest player: card mode, 30 items, journey', st == 200 and 'data-card="1"' in body and body.count('class="ts-q"') == 30
      and 'tsc-journey' in body, str(st))
st, loc, _ = g.req('/start/q/page', [('page', '1'), ('go', 'exit')] + [('q_%s' % i, str(val[f])) for i, f in items[:10]]
                   + [('csrf_token', g.csrf(body))])
check('guest «بعداً» -> /career', st in (302, 303) and path_of(loc) == '/career', loc)
st, loc, body = g.req('/career')
check('/career offers to continue (10 of 60)', 'id="tsc-guest-going"' in body and '۱۰ از ۶۰' in body, str(st))
st, loc, body = g.req('/start/q')
st, loc, _ = g.req('/start/q/page', [('page', '1'), ('go', 'review')] + [('q_%s' % i, str(val[f])) for i, f in items]
                   + [('csrf_token', g.csrf(body))])
check('guest last page -> the result gate', st in (302, 303) and path_of(loc) == '/start/result', loc)
st, loc, body = g.req('/start/result')
check('gate wording for the career list', st == 200 and 'id="tsc-gate-intro"' in body, str(st))
assert g.login(L['g'], pw[L['g']])
st, loc, body = g.req('/start/result')
st, loc, _ = g.req('/start/claim', [('csrf_token', g.csrf(body))])
check('claim -> report', st in (302, 303) and '/my/assessments/' in loc, loc)
st, loc, _ = follow(g, loc)
check('claimed interests open the two questions', st == 200 and 'tsc-bg' in _, str(st))
info = run_info(L['g'])
check('the claim made the run: reminders on, interests done', 'RUN 1 True False True' in info, info.strip()[-80:])
summary()
