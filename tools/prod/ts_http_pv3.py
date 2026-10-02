#!/usr/bin/env python3
"""Portal v3 journeys over HTTP against a served CLONE:  ts_http_pv3.py DB PORT
Home with one next action (invite -> resume -> result -> nothing), four-item navigation, who-sees text from the real
invitation on the consent page, the unavailable-result page, the submission block, the account hub."""
import importlib.util, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
NAMES = ('inv', 'going', 'done', 'empty', 'emp', 'edu', 'hold')
L = {n: 'ts.pv3.%s.http@example.invalid' % n for n in NAMES}
pw = {u: ensure_user(u) for u in L.values()}

code = r"""
L = %r
def user(n): return env['res.users'].search([('login', '=', L[n])])
def panel(name, purpose):
    org = env['res.partner'].search([('name', '=', name)], limit=1) or env['res.partner'].create({'name': name, 'is_company': True})
    org.write({'is_company': True})
    ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create({'name': name, 'purpose': purpose, 'partner_id': org.id})
    ws.write({'approved_on': '2026-01-01 00:00:00'})
    if ws.state in ('draft',):
        ws.state = 'pilot'
    return ws
EDU, EMP = panel('مدرسهٔ نمونهٔ پرتال', 'education'), panel('شرکت نمونهٔ پرتال', 'employment')
inst = env['ts.instrument'].search([('state', '=', 'published'), ('code', '!=', 'TALENT-INV-15')], limit=1)
T, A, C = env['ts.attempt'], env['ts.assignment'], env['ts.panel.client']
def finish(att):
    if att.state == 'consent':
        att.give_consent()
    for it in att.active_items():
        att.save_answer(it.id, 1 + it.id %% 5)
    att.action_submit()
def client_for(ws, u, name):
    return C.search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)], limit=1) or C.create({'workspace_id': ws.id, 'name': name, 'user_id': u.id})
# inv: one open invitation from the school, nothing else
u = user('inv'); cl = client_for(EDU, u, 'دعوت‌شدهٔ پرتال')
ia = A.search([('client_id', '=', cl.id), ('user_id', '=', False)], limit=1) or A.create({'workspace_id': EDU.id, 'instrument_id': inst.id, 'invitee_name': 'دعوت‌شدهٔ پرتال', 'client_id': cl.id, 'deadline': '2027-01-01'})
# going: a self-taken attempt in progress
u = user('going')
ga = T.search([('user_id', '=', u.id), ('state', 'in', ('consent', 'in_progress'))], limit=1)
if not ga:
    ga = T.create({'user_id': u.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id}); ga.give_consent()
    ga.save_answer(ga.active_items()[0].id, 3)
# done: a fresh released result
u = user('done')
da = T.search([('user_id', '=', u.id), ('state', '=', 'done')], limit=1)
if not da:
    da = T.create({'user_id': u.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id}); finish(da)
# emp: invited by the company, accepted with sharing -> consent page pending
u = user('emp'); cl = client_for(EMP, u, 'داوطلب پرتال')
ea = A.search([('client_id', '=', cl.id)], limit=1) or A.create({'workspace_id': EMP.id, 'instrument_id': inst.id, 'invitee_name': 'داوطلب پرتال', 'client_id': cl.id})
if not ea.user_id:
    ea.action_accept(u, True)
# edu: invited by the school, accepted with sharing
u = user('edu'); cl = client_for(EDU, u, 'دانش‌آموز پرتال')
xa = A.search([('client_id', '=', cl.id)], limit=1) or A.create({'workspace_id': EDU.id, 'instrument_id': inst.id, 'invitee_name': 'دانش‌آموز پرتال', 'client_id': cl.id})
if not xa.user_id:
    xa.action_accept(u, True)
# hold: a finished result that is not released
u = user('hold')
ha = T.search([('user_id', '=', u.id), ('state', '=', 'done')], limit=1)
if not ha:
    ha = T.create({'user_id': u.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id}); finish(ha)
ha.write({'released': False})
env.cr.commit()
print('IDS', ia.token, ga.access_token, da.id, ea.attempt_id.access_token, xa.attempt_id.access_token, ha.id)
""" % L
out = shell(code)
mm = re.search(r'IDS (\S+) (\S+) (\d+) (\S+) (\S+) (\d+)', out)
assert mm, out[-1500:]
ITOK, GTOK, DA, ETOK, XTOK, HA = mm.groups()


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


def plain(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))


# ---- home: the one next action follows the real state
st, page = get(login('inv'), '/my')
check('home of an invited person leads with the invitation', st == 200 and 'id="ts-home-next"' in page and 'یک دعوت منتظر شماست' in page, st)
check('…names the school and the deadline', 'مدرسهٔ نمونهٔ پرتال' in page and 'مهلت تا' in page)
check('…and the open invitations list is dated and attributed', 'ts-home-invites' in page and 'از طرف' in page)
st, page = get(login('going'), '/my')
check('home of an unfinished attempt leads with resume', st == 200 and 'یک سنجهٔ نیمه‌تمام دارید' in page and 'ادامهٔ پاسخ‌دهی' in page and 'آخرین ذخیره' in page, st)
st, page = get(login('done'), '/my')
check('home of a fresh result leads with the result', st == 200 and 'نتیجهٔ تازه‌ای آماده است' in page and 'دیدن نتیجه' in page, st)
st, page = get(login('empty'), '/my')
check('home with nothing due is a peaceful state with a path to history', st == 200 and 'id="ts-home-empty"' in page and 'ts-home-next' not in page and 'href="/my/assessments"' in page, st)
nav = re.findall(r'class="tsp-subnav__item[^"]*"', page)
check('the participant navigation has four destinations', len(nav) == 4, len(nav))
check('…and no English or ASCII digits in the home text', not re.search(r'[A-Za-z]{4,}', plain(re.sub(r'(?is)<bdi.*?</bdi>', '', page)).replace('EOT', '')))

# ---- consent: who sees the result, from the invitation
st, page = get(login('going'), '/take/%s' % GTOK)
check('an unfinished attempt opens the player (not the consent page)', st == 200 and 'ts-qform' in page, st)
emp = login('emp')
st, page = get(emp, '/take/%s' % ETOK)
check('consent of a company invitation says the company sees only the band per dimension', st == 200 and 'id="ts-who-sees"' in page and 'فقط بازهٔ هر بُعد' in page and 'شرکت نمونهٔ پرتال' in page, st)
check('…and not the old "only you" sentence', 'با هیچ کارفرما یا مرکزی' not in page)
st, page = get(login('edu'), '/take/%s' % XTOK)
check('consent of a school invitation names the responsible counselor', st == 200 and 'مشاور مسئول' in page and 'مدرسهٔ نمونهٔ پرتال' in page, st)
# a self-started attempt still says "only you"
o = shell("u = env['res.users'].search([('login', '=', %r)]); i = env['ts.instrument'].search([('state', '=', 'published'), ('code', '!=', 'TALENT-INV-15')], limit=1); "
          "a = env['ts.attempt'].search([('user_id', '=', u.id), ('state', '=', 'consent')], limit=1) or env['ts.attempt'].create({'user_id': u.id, 'instrument_id': i.id, 'version_id': i.current_version_id.id}); env.cr.commit(); print('TOK', a.access_token)" % L['empty'])
stok = re.search(r'TOK (\S+)', o).group(1)
st, page = get(login('empty'), '/take/%s' % stok)
check('consent of a self-started attempt says only you', st == 200 and 'فقط شما، در حساب کاربری‌تان' in page, st)

# ---- unavailable result: no redirect loop
h = login('hold')
st, loc, body = h.req('/my/assessments/%s' % HA)
check('a finished result that is not released renders the unavailable page (200, no redirect)', st == 200 and 'در دسترس شما نیست' in body, '%s %s' % (st, loc))
st, body = get(h, '/my/assessments')
check('the list still opens for that person', st == 200, st)

# ---- submission block
d = login('done')
st, page = get(d, '/my/assessments/%s?submitted=1' % DA)
check('after submission the report opens with what was received, who sees it and a next step',
      st == 200 and 'پاسخ‌های شما دریافت و ثبت شد' in page and 'id="ts-who-sees"' in page and 'href="/my"' in page and 'id="ts-summary"' in page, st)
st, page = get(d, '/my/assessments/%s' % DA)
check('without the flag the block is absent', 'پاسخ‌های شما دریافت و ثبت شد' not in page)

# ---- account hub
st, page = get(d, '/my/account')
check('the account page is the hub: notifications, sharing, data, sessions, help, support, sign out',
      st == 200 and all(x in page for x in ('/my/notifications/prefs', '/my/sharing', '/my/privacy', '/my/sessions', '/help', '/contact?topic=support', '/web/session/logout')), st)

summary()
