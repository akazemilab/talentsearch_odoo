#!/usr/bin/env python3
"""Panel self-service over HTTP against a served CLONE.
    ts_http_panel.py DB PORT
Landing/terms, create (school = active, organization = pending approval), pending banner + checklist,
participant invites blocked while pending, colleague invite link bound to one identity, join, revoke,
settings, approval lifts the gate, plus eot.ir isolation."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
import importlib.util
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, path_of, shell = lib.Client, lib.check, lib.ensure_user, lib.path_of, lib.shell

TS = 'talentsearch.ir'
OWN, COL, OTH = 'ts.panel.http.own@example.invalid', 'ts.panel.http.col@example.invalid', 'ts.panel.http.oth@example.invalid'
own_pw, col_pw, oth_pw = ensure_user(OWN), ensure_user(COL), ensure_user(OTH)
shell(
    "for l,p in (('%s','09126660001'),('%s','09126660002'),('%s','09126660003')):\n"
    "    u=env['res.users'].search([('login','=',l)])\n"
    "    u.partner_id.sudo().write({'ts_phone':p})\n"
    "env.cr.commit()\nprint('OK')\n" % (OWN, COL, OTH))
# a clean slate for this user's panels (the clone may be reused)
shell("u=env['res.users'].search([('login','=','%s')])\n"
      "env.cr.execute(\"update ts_workspace_member set create_date = create_date - interval '3 days' where user_id=%%s\", [u.id])\n"
      "env.cr.commit()\nprint('OK')\n" % OWN)

anon = Client(TS)
st, _, page = anon.req('/panel')
check('panel landing is public', st == 200 and '/my/workspaces/new' in page and 'رایگان' in page)
check('landing makes no forbidden claims', not any(w in page for w in ('ضمانت', 'احتمال پذیرش', 'رشتهٔ مناسب')))
st, _, page = anon.req('/panel/terms')
check('terms page shows its version', st == 200 and 'panel-terms-' in page)
st, loc, _ = anon.req('/my/workspaces/new')
check('anonymous create is sent to sign-in', st in (302, 303) and ('/signup' in loc or '/web/login' in loc), loc)

own = Client(TS)
check('owner login', own.login(OWN, own_pw))
st, _, page = own.req('/my/workspaces/new')
check('create form 200: one form (kind, panel name, «نام شما»), the button accepts the terms', st == 200 and 'name="kind"' in page
      and 'name="own_name"' in page and 'name="accept"' in page and '/panel/terms' in page, str(st))
csrf = own.csrf(page)
st, _, bad = own.req('/my/workspaces/new/create', {'csrf_token': csrf, 'name': 'پنل آزمایشی HTTP', 'kind': 'org'})
check('creation without accepting terms is refused with a message', st == 200 and 'شرایط استفاده را بپذیرید' in bad)
st, _, _ = own.req('/my/workspaces/new/create', {'name': 'بدون CSRF', 'kind': 'org', 'terms': '1'})
check('create without CSRF token is rejected', st in (400, 403))
st, loc, _ = own.req('/my/workspaces/new/create', {'csrf_token': csrf, 'name': 'پنل آزمایشی HTTP', 'kind': 'org', 'terms': '1'})
check('organization panel created -> dashboard', st in (302, 303) and '/my/workspaces/' in loc and 'new=1' in loc, loc)
ws_id = re.search(r'/my/workspaces/(\d+)', loc).group(1)
st, _, page = lib.follow(own, loc)
check('a new organization panel is active at once: no approval banner (onb1)', st == 200 and 'در انتظار تأیید' not in page
      and 'پایلوت' not in page)
check('«شروع کار» shown (onb3), without «(پس از تأیید)»', 'id="tso-start"' in page and 'پس از تأیید' not in page)
st, _, legacy = own.req('/my/workspaces/%s/legacy' % ws_id)   # the dashboard has no forms (S6); the old page still does
check('participant invite form available at once', 'id="ts-invite"' in legacy and 'id="ts-pending"' not in legacy)

# colleague invite
st, loc2, _ = own.req('/my/workspaces/%s/members/invite' % ws_id, {'csrf_token': own.csrf(legacy), 'role': 'hr_admin', 'phone': '۰۹۱۲۶۶۶۰۰۰۲'})
check('colleague invite -> shows link', st in (302, 303) and 'minv=' in loc2, loc2)
st, _, page2 = lib.follow(own, loc2)
m = re.search(r'value="https://talentsearch\.ir/join/([0-9a-f]{32})"', page2)
check('join link displayed for copying', bool(m))
tok = m.group(1)
st, loc3, _ = own.req('/my/workspaces/%s/members/invite' % ws_id, {'csrf_token': own.csrf(page2), 'role': 'clinician', 'phone': '09126660009'})
st, _, page3 = own.req('/my/workspaces/%s/legacy' % ws_id)
check('role outside the panel kind refused (flash shown)', 'برای این نوع پنل مجاز نیست' in page3)

st, _, jp = anon.req('/join/' + tok)
check('anonymous join page asks to sign in', st == 200 and 'وارد شوید' in jp and ('/web/login?redirect=' in jp or '/signup?next=' in jp))
oth = Client(TS)
check('other person login', oth.login(OTH, oth_pw))
st, _, jp = oth.req('/join/' + tok)
check('wrong identity cannot accept', st == 200 and 'برای شمارهٔ موبایل یا ایمیل دیگری' in jp and '/accept' not in jp)
check('...the warning and «خروج از این حساب» come first and name the account (UX T7 P10, never «»)',
      'id="ts-join-account"' in jp and 'خروج از این حساب' in jp and '«<bdi></bdi>»' not in jp
      and jp.index('id="ts-join-account"') < jp.index('class="ts-meta"'))
st, _, homepg = oth.req('/my/workspaces/new')
st, loc4, _ = oth.req('/join/%s/accept' % tok, {'csrf_token': oth.csrf(homepg)})
check('direct accept POST by wrong identity refused', st in (302, 303) and '/join/' in loc4, loc4)
col = Client(TS)
check('colleague login', col.login(COL, col_pw))
st, _, jp = col.req('/join/' + tok)
check('right identity sees accept form', st == 200 and '/accept' in jp)
st, loc5, _ = col.req('/join/%s/accept' % tok, {'csrf_token': col.csrf(jp)})
check('accept -> panel dashboard', st in (302, 303) and loc5.endswith('/my/workspaces/' + ws_id) or ('/my/workspaces/' + ws_id) in loc5, loc5)
st, _, cp = col.req('/my/workspaces/' + ws_id + '/legacy')
check('second admin sees the panel', st == 200)
st, _, jp = col.req('/join/' + tok)
check('used link shows invalid', 'دیگر معتبر نیست' in jp)
st, _, _ = anon.req('/join/' + 'f' * 32)
check('unknown join token is 404', st == 404)

# revoke + settings
st, loc6, _ = own.req('/my/workspaces/%s/members/invite' % ws_id, {'csrf_token': own.csrf(page2), 'role': 'hr_admin', 'phone': '09126660008'})
st, _, pg = own.req('/my/workspaces/%s/legacy' % ws_id)   # the old page keeps the old revoke links until S20
rv = re.search(r'/my/workspaces/%s/members/revoke/(\d+)' % ws_id, pg)
check('pending invite can be revoked', bool(rv))
st, _, _ = own.req('/my/workspaces/%s/members/revoke/%s' % (ws_id, rv.group(1)), {'csrf_token': own.csrf(pg)})
st, _, pg = own.req('/my/workspaces/%s/legacy' % ws_id)
check('revoked invite disappears', '/members/revoke/%s' % rv.group(1) not in pg)
st, _, _ = col.req('/my/workspaces/%s/settings' % ws_id, {'csrf_token': col.csrf(cp), 'name': 'نام جدید'})
st, _, pg = own.req('/my/workspaces/' + ws_id + '/legacy')
check('second admin can rename the panel', 'نام جدید' in pg)

# school = active at once
st, _, page = own.req('/my/workspaces/new')
st, loc, _ = own.req('/my/workspaces/new/create', {'csrf_token': own.csrf(page), 'name': 'مدرسهٔ آزمایشی HTTP', 'kind': 'school', 'terms': '1'})
sid = re.search(r'/my/workspaces/(\d+)', loc).group(1)
st, _, sp = own.req('/my/workspaces/%s/legacy' % sid)   # the old page keeps these forms until S20
check('school panel is live: no pending banner, invite form present', 'id="ts-pending"' not in sp and 'id="ts-invite"' in sp)
check('person with two panels gets a panel switcher', 'تغییر پنل' in sp and '/my/workspaces/%s' % ws_id in sp)
st, _, tp = anon.req('/panel/terms')
check('terms explain what happens when a specialist leaves', 'وقتی عضوی از پنل می‌رود' in tp and 'دسترسی اضطراری' in tp)

# the super admin's suspend (replaces approval)
shell("ws=env['ts.workspace'].browse(%s)\nws.action_suspend()\nenv.cr.commit()\nprint('OK')\n" % ws_id)
st, _, pg = own.req('/my/workspaces')
check('suspended panel is marked on the list', st == 200 and 'موقتاً متوقف شده' in pg)
st, _, _ = own.req('/my/workspaces/' + ws_id + '/legacy')
check('suspended panel dashboard is closed', st == 404)

# homepage call-to-action
st, _, home = anon.req('/')
if 'id="tso-hero-start"' in home:
    # onb2 (ts_onboard with a guest starter): the free test leads, the free panel follows
    check('homepage main button is «شروع سنجهٔ رایگان» -> /start', st == 200 and 'href="/start"' in home and 'شروع سنجهٔ رایگان' in home)
    check('homepage secondary button is «ساخت پنل رایگان» -> /panel', 'href="/panel"' in home and 'ساخت پنل رایگان' in home)
else:
    check('homepage main button is «ساخت پنل رایگان» -> /panel', st == 200 and 'href="/panel"' in home and 'ساخت پنل رایگان' in home)
    check('homepage secondary button is «نمونهٔ گزارش» -> /assessments', 'نمونهٔ گزارش' in home and 'href="/assessments#sample"' in home)

# participant shares a finished self-taken result with a counselor panel (by code)
PART = 'ts.panel.http.part@example.invalid'
part_pw = ensure_user(PART)
out = shell(
    "u=env['res.users'].search([('login','=','%s')])\n"
    "inst=env['ts.instrument'].search([('state','=','published'),('purpose','=','employment')],limit=1)\n"
    "at=env['ts.attempt'].create({'user_id':u.id,'instrument_id':inst.id,'version_id':inst.current_version_id.id})\n"
    "at.give_consent()\n"
    "for it in at.active_items(): at.save_answer(it.id, 1 + it.id %% 5)\n"
    "at.action_submit()\n"
    "ws=env['ts.workspace'].browse(%s)\n"
    "env.cr.commit()\nprint('AT', at.id, 'CODE', ws.code)\n" % (PART, sid))
at_id, code = re.search(r'AT (\d+) CODE (\S+)', out).groups()
pc = Client(TS)
check('participant login', pc.login(PART, part_pw))
st, _, rep = pc.req('/my/assessments/' + at_id)
check('result page offers sending to my counselor', st == 200 and 'ارسال نتیجه برای مشاورم' in rep and '/share' in rep, str(st))
st, _, fm = pc.req('/my/assessments/%s/share' % at_id)
check('share form asks for a panel code', st == 200 and 'name="code"' in fm)
st, _, bad = pc.req('/my/assessments/%s/share?code=TSW-99999' % at_id)
check('unknown code is refused with a message', 'پنلی با این کد پیدا نشد' in bad)
st, _, ok = pc.req('/my/assessments/%s/share?code=%s' % (at_id, code))
check('known code shows the panel name for confirmation', 'مدرسهٔ آزمایشی HTTP' in ok and '/share/confirm' in ok)
st, loc, _ = pc.req('/my/assessments/%s/share/confirm' % at_id, {'csrf_token': pc.csrf(ok), 'code': code})
check('confirm -> back to the result', st in (302, 303) and loc.endswith('/my/assessments/' + at_id) or ('/my/assessments/' + at_id) in loc, loc)
st, _, rep = pc.req('/my/assessments/' + at_id)
check('result page now says it was sent, with a stop button', 'فرستاده‌اید' in rep and '/unshare' in rep)
st, _, _ = pc.req('/my/assessments/%s/share/confirm' % at_id, {'code': code})
check('confirm without CSRF is rejected', st in (400, 403))
st, _, other = anon.req('/my/assessments/%s/share' % at_id)
check('anonymous cannot open the share page', st in (302, 303, 404))
st, _, _ = oth.req('/my/assessments/%s/share' % at_id)
check('another account cannot open my share page', st == 404)
st, _, sp = own.req('/my/workspaces/' + sid + '/legacy')
check('the panel sees the shared result in its unassigned queue', st == 200 and 'href="?resp=none"' in sp)
st, loc, _ = pc.req('/my/assessments/%s/unshare' % at_id, {'csrf_token': pc.csrf(rep)})
st, _, rep = pc.req('/my/assessments/' + at_id)
check('participant can stop sharing', 'نتیجه با پنل به اشتراک گذاشته نشده است' in rep)

# eot.ir isolation
e = Client('www.eot.ir')
for path in ('/panel', '/panel/terms', '/join/' + tok, '/my/workspaces/new'):
    st = e.req(path)[0]
    check('eot.ir %s not served' % path[:12], st in (404, 303, 302), str(st))
lib.summary()
