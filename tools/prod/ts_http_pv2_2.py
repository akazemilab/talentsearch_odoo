#!/usr/bin/env python3
"""Panel v2 S2 (shell) over HTTP against a served CLONE:  ts_http_pv2_2.py DB PORT
Menu per role, settings page and its POST, state pages, header link, notice on the old page."""
import importlib.util, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell
TS = 'talentsearch.ir'
NAMES = ('owner', 'admin', 'counselor', 'hr', 'hm', 'unv', 'nopanel', 'outsider', 'multi')
L = {n: 'ts.pv2s2.%s.http@example.invalid' % n for n in NAMES}
pw = {u: ensure_user(u) for u in L.values()}
code = r'''
L = %r
def user(n): return env['res.users'].search([('login', '=', L[n])])
def panel(name, purpose):
    org = env['res.partner'].search([('name', '=', name)], limit=1) or env['res.partner'].create({'name': name, 'is_company': True})
    org.write({'is_company': True})
    ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create(
        {'name': name, 'purpose': purpose, 'partner_id': org.id, 'escalation_contact_id': org.id if purpose == 'clinical' else False})
    ws.write({'approved_on': '2026-01-01 00:00:00'}); ws.state = 'pilot'
    return ws
def member(ws, n, role):
    u = user(n)
    m = env['ts.workspace.member'].search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)]) or env['ts.workspace.member'].create(
        {'workspace_id': ws.id, 'user_id': u.id, 'role': role})
    if m.role != role: m.role = role
    if role in ('counselor', 'clinician') and n != 'unv':
        m.write({'license_number': 'T-1', 'verification_state': 'verified'})
    return m
A = panel('پنل S2 آموزشی', 'education'); B = panel('پنل S2 استخدامی', 'employment'); C = panel('پنل S2 بالینی', 'clinical')
member(A, 'owner', 'owner'); member(A, 'admin', 'admin'); member(A, 'counselor', 'counselor')
member(B, 'hr', 'hr_admin'); member(B, 'hm', 'hiring_manager'); member(B, 'owner', 'owner')
member(B, 'multi', 'owner'); member(A, 'multi', 'counselor')
member(C, 'unv', 'clinician'); member(C, 'owner', 'owner')
env.cr.commit()
print('IDS', A.id, B.id, C.id)
''' % L
out = shell(code)
mm = re.search(r'IDS (\d+) (\d+) (\d+)', out)
assert mm, out[-1500:]
A, B, C = mm.groups()


def login(n):
    c = Client(TS)
    assert c.login(L[n], pw[L[n]]), n
    return c


def menu(page):
    return [re.sub(r'\s+', ' ', t).strip() for t in re.findall(r'<a[^>]*class="tsp-nav__item"[^>]*>(.*?)</a>', page, re.S)]


BASE = ['داشبورد', 'دعوت و فهرست (نسخهٔ قبلی)']
HELP = ['راهنما']
SETT = ['تنظیمات']
MEM = ['اعضا و نقش‌ها']
CLI = ['شرکت‌کنندگان']
want = {
    ('owner', A): BASE + CLI + MEM + SETT + HELP, ('admin', A): BASE + CLI + MEM + HELP, ('counselor', A): BASE + CLI + HELP,
    ('hr', B): BASE + CLI + MEM + SETT + HELP, ('hm', B): BASE + CLI + HELP,
}
pages = {}
for (n, w), items in want.items():
    c = login(n)
    st, _, page = c.req('/my/workspaces/%s/home' % w)
    pages[(n, w)] = (c, page)
    check('%s: dashboard opens' % n, st == 200 and 'Traceback' not in page, str(st))
    check('%s: menu has exactly the items of its permissions, help last' % n, menu(page) == items, str(menu(page)))
    check('%s: one h1, Persian title with panel name' % n, page.count('<h1') == 1 and re.search(r'<title>[^<]*داشبورد[^<]*پنل S2', page) is not None)

# tiles
c, page = pages[('owner', A)]
check('dashboard shows the six counters as links to the filtered list',
      all(('state=%s' % k) in page for k in ('invited', 'accepted', 'in_progress', 'done', 'declined', 'withdrawn'))
      and 'تکمیل‌شده' in page and 'class="tsp-stat"' in page)
check('current menu item is marked', 'aria-current="page"' in page)
check('pill states the panel is active (word, not colour only)', 'ts-pill--ok' in page and 'فعال' in page)

# settings: permission matrix
for n, w, ok in (('owner', A, True), ('hr', B, True), ('counselor', A, False), ('admin', A, False), ('hm', B, False)):
    c, _ = pages[(n, w)]
    st, _, page = c.req('/my/workspaces/%s/settings' % w)
    if ok:
        check('%s opens settings' % n, st == 200 and 'id="tsp_name"' in page and menu(page).count('تنظیمات') == 1, str(st))
    else:
        check('%s gets the 403 page inside the shell' % n, st == 403 and 'به این بخش دسترسی ندارید' in page and 'tsp-nav' in page, str(st))
c, _ = pages[('owner', A)]
st, _, page = c.req('/my/workspaces/%s/settings' % A)
check('owner sees contact and terms sections', 'id="tsp-contact"' in page and 'id="tsp-terms"' in page)
c, _ = pages[('hr', B)]
st, _, page = c.req('/my/workspaces/%s/settings' % B)
check('hr_admin (panel:profile only) does not see the terms section', 'id="tsp-profile"' in page and 'id="tsp-terms"' not in page)

# settings POST
c, _ = pages[('owner', A)]
st, _, page = c.req('/my/workspaces/%s/settings' % A)
csrf = c.csrf(page)
st, loc, _ = c.req('/my/workspaces/%s/settings/save' % A, {'name': 'پنل S2 آموزشی', 'csrf_token': csrf})
check('owner saves settings (redirect to the settings page)', st in (302, 303) and (loc or '').endswith('/settings'), '%s %s' % (st, loc))
st, _, page = c.req('/my/workspaces/%s/settings' % A)
check('the next page says it was saved', 'تغییرها ذخیره شد' in page and 'role="status"' in page)
st, loc, _ = c.req('/my/workspaces/%s/settings/save' % A, {'name': 'x', 'csrf_token': csrf})
st, _, page = c.req('/my/workspaces/%s/settings' % A)
check('a too short name is refused with a message and the value is kept', 'نام پنل باید بین' in page and 'role="alert"' in page)
st, _, _ = c.req('/my/workspaces/%s/settings/save' % A, {'name': 'پنل S2 آموزشی'})
check('POST without CSRF is refused', st in (400, 403), str(st))
c, _ = pages[('hr', B)]
st, _, page = c.req('/my/workspaces/%s/settings' % B)
st, loc, _ = c.req('/my/workspaces/%s/settings/save' % B, {'name': 'پنل S2 استخدامی', 'csrf_token': c.csrf(page)})
check('hr_admin saves settings', st in (302, 303), str(st))
c, cpage = pages[('counselor', A)]
st, _, _ = c.req('/my/workspaces/%s/settings/save' % A, {'name': 'هک', 'csrf_token': c.csrf(c.req('/my/workspaces/new')[2])})
check('counselor settings POST is a 403', st == 403, str(st))
name = shell("print('NAME', env['ts.workspace'].browse(%s).name)" % A)
check('and the name did not change', 'NAME پنل S2 آموزشی' in name, name[-60:])

# unverified clinician
u = login('unv')
st, _, page = u.req('/my/workspaces/%s/home' % C)
check('unverified clinician sees the notice page at W/home', st == 200 and 'در حال بررسی است' in page and menu(page) == ['داشبورد', 'راهنما'], '%s %s' % (st, menu(page)))
check('the old page still answers 404 for them', u.req('/my/workspaces/%s' % C)[0] == 404)
check('and settings is 403', u.req('/my/workspaces/%s/settings' % C)[0] == 403)

# suspended panel
shell("w = env['ts.workspace'].browse(%s); w.state = 'suspended'; env.cr.commit()" % B)
st, _, page = pages[('hr', B)][0].req('/my/workspaces/%s/home' % B)
check('suspended panel shows its notice page', st == 200 and 'موقتاً معلق' in page and menu(page) == ['داشبورد', 'راهنما'], '%s %s' % (st, menu(page)))
shell("w = env['ts.workspace'].browse(%s); w.state = 'pilot'; env.cr.commit()" % B)

# strangers
o = login('outsider')
check('a stranger gets 404 on dashboard and settings', o.req('/my/workspaces/%s/home' % A)[0] == 404 and o.req('/my/workspaces/%s/settings' % A)[0] == 404)
n_ev = shell("print('N', env['ts.audit.event'].search_count([('event_type','=','authz.deny'),('workspace_id','=',%s)]))" % A)
check('denials are in the audit trail', int(re.search(r'N (\d+)', n_ev).group(1)) >= 1, n_ev[-20:])
e = Client('www.eot.ir'); e.login(L['owner'], pw[L['owner']])
check('eot.ir has no panel pages (signed in)', e.req('/my/workspaces/%s/home' % A)[0] == 404)
check('anonymous visitor is sent to sign in', Client(TS).req('/my/workspaces/%s/home' % A)[0] in (302, 303))

# header link «پنل من»
st, _, home = login('counselor').req('/')
check('header link «پنل من» for a single-panel member goes straight to the panel',
      'پنل من' in home and ('/my/workspaces/%s/home' % A) in home)
st, _, home = login('multi').req('/')
check('header link for a member of several panels goes to the list', re.search(r'href="/my/workspaces"[^>]*>پنل من', home) is not None)
st, _, home = login('nopanel').req('/')
check('a person without a panel has no «پنل من»', 'پنل من' not in home)
check('anonymous header has no «پنل من»', 'پنل من' not in Client(TS).req('/')[2])

# old pages
c, _ = pages[('owner', A)]
st, _, old = c.req('/my/workspaces/%s' % A)
check('old panel page shows the notice with a link to the new dashboard', st == 200 and ('/my/workspaces/%s/home' % A) in old and 'داشبورد و تنظیمات پنل' in old, str(st))
st, _, lst = c.req('/my/workspaces')
check('panel list enters the new dashboard', st == 200 and ('/my/workspaces/%s/home' % A) in lst)
summary()
