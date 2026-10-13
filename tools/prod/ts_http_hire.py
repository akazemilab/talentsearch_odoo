#!/usr/bin/env python3
"""HR hiring over HTTP against a served CLONE:  ts_http_hire.py DB PORT

An HR admin of an employment panel creates a position (search -> pick occupation -> short battery), reviews the
requirement profile (one critical), invites a candidate from the position page (no SMS/email leaves a clone); the
candidate opens the invitation (position card, optional fairness questions), accepts, answers the personality
questionnaire through the normal POST routes, plays the reasoning task through the task endpoints, sees the feedback card;
HR sees the candidate in the list with a band, opens the candidate page, records a decision, opens compare and fairness;
a reviewer cannot record a decision (403); the public catalog does not list the invite-only instruments."""
import importlib.util
import json
import os
import re
import sys
import html as H

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
L = {n: 'ts.hire.%s.http@example.invalid' % n for n in ('hr', 'rev', 'cand', 'cand2')}
pw = {u: ensure_user(u) for u in L.values()}

out = shell(r"""
L = %r
def user(n): return env['res.users'].search([('login', '=', L[n])])
name = 'شرکت آزمون استخدام وب'
org = env['res.partner'].search([('name', '=', name)], limit=1) or env['res.partner'].create({'name': name, 'is_company': True})
ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create(
    {'name': name, 'purpose': 'employment', 'partner_id': org.id})
ws.state = 'active'
def member(n, role):
    u = user(n)
    m = env['ts.workspace.member'].with_context(active_test=False).search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)]) \
        or env['ts.workspace.member'].create({'workspace_id': ws.id, 'user_id': u.id, 'role': role})
    m.write({'active': True, 'role': role})
    return m
mh = member('hr', 'hr_admin'); mr = member('rev', 'reviewer')
env['ts.hire.position'].sudo().search([('workspace_id', '=', ws.id)]).write({'state': 'closed'})
env['ir.config_parameter'].sudo().set_str('ts_panel.invites_per_hour', '200')
env.cr.commit()
print('IDS', ws.id, mh.id, mr.id)
""" % L)
mm = re.search(r'IDS (\d+) (\d+) (\d+)', out)
assert mm, out[-1500:]
WS = mm.group(1)
W = '/my/workspaces/%s' % WS


def login(n):
    c = Client(TS)
    assert c.login(L[n], pw[L[n]]), n
    return c


def get(c, path):
    for _ in range(4):
        st, loc, body = c.req(path)
        if st in (301, 302, 303) and loc:
            path = path_of(loc)
            continue
        break
    return st, body


def post(c, path, data):
    pairs = list(data.items()) if isinstance(data, dict) else list(data)
    pairs.append(('csrf_token', c.csrf(c.req('/web/login')[2])))
    return c.req(path, pairs)


hr, rev, cand = login('hr'), login('rev'), login('cand')

# ---------------------------------------------------------------- 1. position: search, create, profile
st, body = get(hr, W + '/positions')
check('HR sees the positions page with the menu entry', st == 200 and 'موقعیت‌های شغلی' in body and '/positions/new' in body, str(st))
st, body = get(hr, W + '/positions/new?q=' + 'توسعه نرم افزار')
occ = re.search(r'name="occupation_id"[^>]*value="(\d+)"', body)
check('Persian search finds the software developer (ZWNJ-insensitive)', st == 200 and occ and 'توسعه‌دهندهٔ نرم‌افزار' in body, str(st))
st, loc, _ = post(hr, W + '/positions/new', {'name': 'برنامه‌نویس وب آزمون', 'occupation_id': occ.group(1) if occ else '0',
                                              'battery_choice': 'short', 'deadline': ''})
pm = re.search(r'/positions/(\d+)/profile', loc)
check('creating the position opens the requirement profile', st in (302, 303) and pm, loc)
PID = pm.group(1) if pm else '0'
B = W + '/positions/%s' % PID
st, body = get(hr, B + '/profile')
check('profile lists work styles and abilities with checkboxes and the O*NET credit',
      st == 200 and 'دقت در جزئیات' in body and 'name="critical"' in body and 'CC BY' in body, str(st))
st, loc, _ = post(hr, B + '/profile', [('critical', 'Attention to Detail'), ('dropped', 'Social Orientation')])
check('saving the profile goes to the candidates page', st in (302, 303) and loc.rstrip('/').endswith('/positions/%s' % PID), loc)

# ---------------------------------------------------------------- 2. invite
st, loc, _ = post(hr, B + '/invite', {'people': 'داوطلب آزمون وب، cand.http@example.invalid', 'send_sms': '1',
                                       'send_email': '1', 'extra_time': '1.0'})
st, body = get(hr, B)
check('the invitation is listed under the position', st == 200 and 'داوطلب آزمون وب' in body and '۱ دعوت' in body.replace('<strong>', '').replace('</strong>', ''), str(st))
out = shell("a = env['ts.assignment'].sudo().search([('position_id', '=', %s)], limit=1); print('TOK', a.token, a.id, a.battery_id.code, bool(a.email_error))" % PID)
tm = re.search(r'TOK ([0-9a-f]{32}) (\d+) (\S+) (\w+)', out)
check('the invitation is a battery invitation for the position (email not sent on a clone, error recorded)',
      tm and tm.group(3) == 'BAT-HR-SHORT' and tm.group(4) == 'True', out[-300:])
TOKEN, AID = (tm.group(1), tm.group(2)) if tm else ('x', '0')
st, body = get(rev, B + '/c/%s' % AID)
check('a reviewer can open the candidate before results (status only, no band)', st == 200 and 'tsh-band--' not in body, str(st))

# ---------------------------------------------------------------- 3. candidate side
st, body = get(cand, '/invite/%s' % TOKEN)
check('the welcome screen names the position, says what the employer sees, «روی کامپیوتر بهتر است» for the timed part, '
      'and asks no fairness question at the start (onb2: they come at the end)',
      st == 200 and 'برای موقعیت' in body and 'خلاصهٔ تناسب' in body and 'روی کامپیوتر بهتر است' in body and 'name="ts_gender"' not in body, str(st))
# UX T7 P26: one description of what the employer sees (tick, list and card agree with result_level/_row), the timed task
# is counted in sections (never «۰ پرسش»), and the time is stated once from data (no description minutes beside it)
check('one truthful disclosure: the tick names factor levels, the job-fit summary and the integrity signals; no «only levels» line',
      'خلاصهٔ تناسبم با این شغل و نشانه‌های دقت پاسخ‌دهی را ببیند' in body
      and 'فقط سطح هر عامل (کم، متوسط یا زیاد) را می‌بیند' not in body, str(st))
check('the timed task is counted in timed sections, never «۰ پرسش», and minutes appear only from data (effort_facts)',
      'بخش زمان‌دار' in body and not re.search(r'(?<![۰-۹])۰ پرسش', body) and 'استدلال؛ حدود' not in body and 'tso-facts' in body, str(st))
st, loc, _ = post(cand, '/invite/%s/accept' % TOKEN, {'share': '1'})
check('accepting opens the player', st in (302, 303) and '/take/' in loc, loc)
out = shell("a = env['ts.assignment'].sudo().browse(%s); print('DEMO', a.ts_gender or '-', a.ts_age_band or '-', '|'.join(t.access_token for t in a.ts_battery_attempts()))" % AID)
dm = re.search(r'DEMO (\S+) (\S+) (\S+)', out)
check('nothing about gender or age is stored at the start', dm and dm.group(1) == '-' and dm.group(2) == '-', out[-200:])
T1, T2 = dm.group(3).split('|') if dm else ('x', 'y')
st, body = get(cand, '/take/%s' % T1)
check('one consent page for the battery', st == 200 and 'consent_service' in body, str(st))
post(cand, '/take/%s/consent' % T1, {'consent_service': '1'})
ids = shell("t = env['ts.attempt'].sudo().search([('access_token', '=', '%s')]); print('ITEMS', ','.join('%%s:%%s' %% (i.id, 1 if i.factor_id.code == 'ATTN' else 3) for i in t.active_items()))" % T1)
im = re.search(r'ITEMS ([\d:,]+)', ids)
pairs = [tuple(x.split(':')) for x in im.group(1).split(',')] if im else []
for k in range(0, len(pairs), 10):
    post(cand, '/take/%s/page' % T1, [('page', str(k // 10 + 1)), ('go', 'next')] + [('q_%s' % i, v) for i, v in pairs[k:k + 10]])
st, loc, _ = post(cand, '/take/%s/submit' % T1, {})
check('the questionnaire is submitted and the battery moves on', st in (302, 303) and ('/next' in loc or '/take/' in loc), loc)
st, body = get(cand, '/take/%s' % T2)
check('the task player page renders with its config', st == 200 and 'tst-player' in body and 'data-config=' in body, str(st))
cfg = json.loads(H.unescape(re.search(r'data-config="([^"]*)"', body).group(1))) if 'data-config=' in body else {}
check('config has three blocks, practice items with keys, no live items', len(cfg.get('blocks', [])) == 3
      and cfg['blocks'][0]['practice']['keys'] and 'items' not in cfg['blocks'][0], str(list(cfg)[:5]))
check('the task player names the inviting organisation and what it sees; the overview gets the total minutes',
      'tst-who' in body and 'data-org=' in body and cfg.get('minutes') == 12 and 'پایین‌چپ' not in body
      # verify T7: the same who-sees sentence as the invitation and consent, never «فقط خلاصهٔ تناسب»
      and 'id="ts-who-sees-line"' in body and 'نشانه‌های دقت پاسخ‌دهی' in body and 'فقط خلاصهٔ تناسب' not in body, str(cfg.get('minutes')))
for i in range(3):
    st, _, rb = post(cand, '/take/%s/task/start' % T2, {'i': str(i)})
    j = json.loads(rb) if st == 200 else {}
    if i == 0:
        check('starting a block returns items without answers', st == 200 and j.get('items') and all('key' not in x for x in j['items']), str(st))
    for idx in range(len(j.get('items', []))):
        post(cand, '/take/%s/task/answer' % T2, {'i': str(i), 'idx': str(idx), 'c': '0', 'rt': '3500'})
    st, _, rb = post(cand, '/take/%s/task/finish' % T2, {'i': str(i), 'focus_lost': '0'})
fin = json.loads(rb) if st == 200 else {}
check('the last block returns the battery result URL', fin.get('url', '').startswith('/my/assessments/battery/'), rb[-200:])
st, body = get(cand, fin.get('url', '/my'))
check('after the last part the two optional fairness questions come once, before the feedback, with «رد شدن»',
      st == 200 and 'name="ts_gender"' in body and 'name="ts_age_band"' in body and 'رد شدن' in body and 'بازخورد شما' not in body, str(st))
st, loc, _ = post(cand, '/my/assessments/battery/%s/about/save' % AID, {'ts_gender': 'female', 'ts_age_band': '25-34'})
out = shell("a = env['ts.assignment'].sudo().browse(%s); print('DEMO', a.ts_gender or '-', a.ts_age_band or '-', a.ts_fair_asked)" % AID)
check('the optional answers are stored as before (same fields, EOT team only)', 'DEMO female 25-34 True' in out, out[-200:])
st, body = get(cand, path_of(loc) if loc else '/my')
check('then the candidate sees the feedback card and the percentile column', st == 200 and 'بازخورد شما' in body and 'صدک' in body, str(st))
st, body = get(cand, '/my/assessments/battery/%s' % AID)
check('the questions are asked once: the battery page opens directly the next time', st == 200 and 'name="ts_gender"' not in body
      and 'بازخورد شما' in body, str(st))
st, loc, _ = post(cand, '/my/assessments/battery/%s/about/save' % AID, {'ts_gender': 'male'})
check('a second answer is not taken', 'DEMO female' in shell("a = env['ts.assignment'].sudo().browse(%s); print('DEMO', a.ts_gender)" % AID))
st, body = get(cand, '/assessments?all=1')
check('the public catalog does not list the invite-only instruments', st == 200 and 'پرسش‌نامهٔ سبک‌های کاری' not in body
      and 'آزمون استدلال' not in body, str(st))

# ---------------------------------------------------------------- 4. HR: list, candidate, decision, compare, fairness
st, body = get(hr, B)
check('the list shows a fit band for the finished candidate', st == 200 and re.search(r'tsh-band tsh-band--(strong|moderate|limited)', body), str(st))
st, body = get(hr, B + '/c/%s' % AID)
check('the candidate page shows reasons, requirement table and decision form, never scores',
      st == 200 and 'سبک‌های کاری' in body and 'name="decision"' in body and 'صدک' not in body, str(st))
st, loc, _ = post(hr, B + '/c/%s/decision' % AID, {'decision': 'interview', 'note': 'مصاحبهٔ فنی'})
out = shell("print('DEC', env['ts.assignment'].sudo().browse(%s).hire_decision)" % AID)
check('the decision is stored', 'DEC interview' in out, out[-100:])
st, _, _ = post(rev, B + '/c/%s/decision' % AID, {'decision': 'reject'})
check('a reviewer cannot record a decision (403)', st == 403, str(st))
st, body = get(hr, B + '/compare?ids=%s' % AID)
check('compare needs two candidates (redirect with a message)', st == 200 and 'دو یا سه داوطلب' in body, str(st))
st, body = get(hr, B + '/fairness')
check('fairness page renders with the small-group rule', st == 200 and 'قاعدهٔ چهارپنجم' in body, str(st))
st, body = get(rev, B + '/fairness')
check('a reviewer may read the fairness view (reports:group)', st == 200, str(st))
other = login('cand2')
st, _ = get(other, B)
check('a non-member gets 404 on the position', st == 404, str(st))
st, _, _ = post(other, '/take/%s/task/start' % T2, {'i': '0'})
check('another user cannot drive the candidate\'s task (404)', st == 404, str(st))
# a finished candidate who did NOT share: no band, no place among the ranked, not counted
out = shell(r'''
import json
p = env['ts.hire.position'].browse(%s)
u = env['res.users'].search([('login', '=', '%s')])
A = env['ts.assignment'].sudo()
x = A.search([('position_id', '=', p.id), ('invitee_name', '=', 'داوطلب بی‌اشتراک')], limit=1) or A.create({
    'workspace_id': p.workspace_id.id, 'battery_id': p.battery_id.id, 'position_id': p.id,
    'instrument_id': p.battery_id.ts_first_instrument().id, 'invitee_name': 'داوطلب بی‌اشتراک'})
if not x.user_id:
    x.action_accept(u, share=False)
for t in x.ts_battery_attempts():
    if t.state == 'consent':
        t.give_consent()
    if t.state == 'in_progress' and t.version_id.mode != 'task':
        for it in t.active_items():
            t.save_answer(it.id, 5 if not it.reverse else 1)
        t.action_submit()
    elif t.state == 'in_progress':
        st = json.loads(t.task_json or '{}') or t._ts_state()
        for i in range(len(t.ts_task_spec()['blocks'])):
            t.ts_task_start(i)
            for idx, k in enumerate(t._ts_items(json.loads(t.task_json), i)[1]):
                t.ts_task_answer(i, idx, k, 3000)
            t.ts_task_finish(i)
env.cr.commit()
print('NOSHARE', x.id, x.jobfit_band or '-', x.share_level)
''' % (PID, L['cand2']))
ns = re.search(r'NOSHARE (\d+) (\S+) (\S+)', out)
check('fixture: a finished non-sharing candidate with a computed band', ns and ns.group(2) != '-' and ns.group(3) == 'none', out[-300:])
st, body = get(hr, B)
NID = ns.group(1) if ns else '0'
row = re.search(r'/c/%s".*?</tr>' % NID, body, re.S)
check('the non-sharing candidate shows no band in the list', row and 'tsh-band--' not in row.group(0), str(bool(row)))
pos_shared, pos_ns = body.find('/c/%s"' % AID), body.find('/c/%s"' % NID)
check('the non-sharing candidate is listed after the ranked ones', 0 < pos_shared < pos_ns, (pos_shared, pos_ns))
st, body = get(hr, B + '/c/%s' % NID)
check('the non-sharing candidate page shows no fit', st == 200 and 'tsh-band--' not in body and 'اشتراک‌گذاری نتیجه را نپذیرفته' in body, str(st))
st, body = get(hr, B + '/compare?ids=%s&ids=%s' % (AID, NID))
check('compare ignores a candidate without a shared result', 'دو یا سه داوطلب' in body, str(st))
out = shell("o = env['ts.assignment'].sudo().search([('position_id', '!=', %s), ('position_id', '!=', False)], limit=1); print('OTHER', o.id or 0)" % PID)
oth = re.search(r'OTHER (\d+)', out)
if oth and oth.group(1) != '0':
    st, _ = get(hr, B + '/c/%s' % oth.group(1))
    check('a candidate of another position or panel is 404', st == 404, str(st))
eot = Client('eot.ir')
eot.login(L['hr'], pw[L['hr']])
st, _, _ = eot.req(W + '/positions')
check('the HR routes do not answer on eot.ir', st == 404, str(st))

summary()
