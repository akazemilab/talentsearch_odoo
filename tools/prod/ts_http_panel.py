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
    "for l,p in (('%s','09127770001'),('%s','09127770002'),('%s','09127770003')):\n"
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
check('create form 200', st == 200 and 'name="kind"' in page and 'name="terms"' in page, str(st))
csrf = own.csrf(page)
st, _, bad = own.req('/my/workspaces/new/create', {'csrf_token': csrf, 'name': 'پنل آزمایشی HTTP', 'kind': 'org'})
check('creation without accepting terms is refused with a message', st == 200 and 'شرایط استفاده را بپذیرید' in bad)
st, _, _ = own.req('/my/workspaces/new/create', {'name': 'بدون CSRF', 'kind': 'org', 'terms': '1'})
check('create without CSRF token is rejected', st in (400, 403))
st, loc, _ = own.req('/my/workspaces/new/create', {'csrf_token': csrf, 'name': 'پنل آزمایشی HTTP', 'kind': 'org', 'terms': '1'})
check('organization panel created -> dashboard', st in (302, 303) and '/my/workspaces/' in loc and 'new=1' in loc, loc)
ws_id = re.search(r'/my/workspaces/(\d+)', loc).group(1)
st, _, page = own.req(path_of(loc))
check('pending banner shown', st == 200 and 'در انتظار تأیید' in page)
check('checklist shown', 'گام‌های راه‌اندازی' in page and 'پس از تأیید' in page)
check('participant invite form hidden while pending', 'id="ts-invite"' not in page)
st, loc2, _ = own.req('/my/workspaces/%s/invite' % ws_id, {'csrf_token': own.csrf(page), 'invitee_name': 'x', 'instrument_id': '1'})
check('participant invite POST refused while pending', 'error=' in loc2, loc2)

# colleague invite
st, loc2, _ = own.req('/my/workspaces/%s/members/invite' % ws_id, {'csrf_token': own.csrf(page), 'role': 'hr_admin', 'phone': '۰۹۱۲۷۷۷۰۰۰۲'})
check('colleague invite -> shows link', st in (302, 303) and 'minv=' in loc2, loc2)
st, _, page2 = own.req(path_of(loc2))
m = re.search(r'value="https://talentsearch\.ir/join/([0-9a-f]{32})"', page2)
check('join link displayed for copying', bool(m))
tok = m.group(1)
st, loc3, _ = own.req('/my/workspaces/%s/members/invite' % ws_id, {'csrf_token': own.csrf(page2), 'role': 'clinician', 'phone': '09127770009'})
st, _, page3 = own.req('/my/workspaces/%s' % ws_id)
check('role outside the panel kind refused (flash shown)', 'برای این نوع پنل مجاز نیست' in page3)

st, _, jp = anon.req('/join/' + tok)
check('anonymous join page asks to sign in', st == 200 and 'وارد شوید' in jp and '/web/login?redirect=' in jp)
oth = Client(TS)
check('other person login', oth.login(OTH, oth_pw))
st, _, jp = oth.req('/join/' + tok)
check('wrong identity cannot accept', st == 200 and 'برای شمارهٔ موبایل یا ایمیل دیگری' in jp and '/accept' not in jp)
st, loc4, _ = oth.req('/join/%s/accept' % tok, {'csrf_token': oth.csrf(jp)})
check('direct accept POST by wrong identity refused', st in (302, 303) and '/join/' in loc4, loc4)
col = Client(TS)
check('colleague login', col.login(COL, col_pw))
st, _, jp = col.req('/join/' + tok)
check('right identity sees accept form', st == 200 and '/accept' in jp)
st, loc5, _ = col.req('/join/%s/accept' % tok, {'csrf_token': col.csrf(jp)})
check('accept -> panel dashboard', st in (302, 303) and loc5.endswith('/my/workspaces/' + ws_id) or ('/my/workspaces/' + ws_id) in loc5, loc5)
st, _, cp = col.req('/my/workspaces/' + ws_id)
check('second admin sees the panel', st == 200)
st, _, jp = col.req('/join/' + tok)
check('used link shows invalid', 'دیگر معتبر نیست' in jp)
st, _, _ = anon.req('/join/' + 'f' * 32)
check('unknown join token is 404', st == 404)

# revoke + settings
st, loc6, _ = own.req('/my/workspaces/%s/members/invite' % ws_id, {'csrf_token': own.csrf(page2), 'role': 'hr_admin', 'phone': '09127770008'})
st, _, pg = own.req('/my/workspaces/' + ws_id)
rv = re.search(r'/my/workspaces/%s/members/revoke/(\d+)' % ws_id, pg)
check('pending invite can be revoked', bool(rv))
st, _, _ = own.req('/my/workspaces/%s/members/revoke/%s' % (ws_id, rv.group(1)), {'csrf_token': own.csrf(pg)})
st, _, pg = own.req('/my/workspaces/' + ws_id)
check('revoked invite disappears', '/members/revoke/%s' % rv.group(1) not in pg)
st, _, _ = col.req('/my/workspaces/%s/settings' % ws_id, {'csrf_token': col.csrf(cp), 'name': 'نام جدید'})
st, _, pg = own.req('/my/workspaces/' + ws_id)
check('second admin can rename the panel', 'نام جدید' in pg)

# school = active at once
st, _, page = own.req('/my/workspaces/new')
st, loc, _ = own.req('/my/workspaces/new/create', {'csrf_token': own.csrf(page), 'name': 'مدرسهٔ آزمایشی HTTP', 'kind': 'school', 'terms': '1'})
sid = re.search(r'/my/workspaces/(\d+)', loc).group(1)
st, _, sp = own.req(path_of(loc))
check('school panel is live: no pending banner, invite form present', 'id="ts-pending"' not in sp and 'id="ts-invite"' in sp)

# platform approval lifts the gate
shell("ws=env['ts.workspace'].browse(%s)\nws.action_approve()\nenv.cr.commit()\nprint('OK')\n" % ws_id)
st, _, pg = own.req('/my/workspaces/' + ws_id)
check('after approval banner is gone and invite form appears', 'id="ts-pending"' not in pg and 'id="ts-invite"' in pg)
shell("ws=env['ts.workspace'].browse(%s)\nws.action_suspend()\nenv.cr.commit()\nprint('OK')\n" % ws_id)
st, _, pg = own.req('/my/workspaces')
check('suspended panel is marked on the list', st == 200 and 'تعلیق شده' in pg)
st, _, _ = own.req('/my/workspaces/' + ws_id)
check('suspended panel dashboard is closed', st == 404)

# eot.ir isolation
e = Client('www.eot.ir')
for path in ('/panel', '/panel/terms', '/join/' + tok, '/my/workspaces/new'):
    st = e.req(path)[0]
    check('eot.ir %s not served' % path[:12], st in (404, 303, 302), str(st))
lib.summary()
