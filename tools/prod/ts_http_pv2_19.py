#!/usr/bin/env python3
"""Panel v2 S19 (help center, contextual help, text and accessibility scan) over HTTP against a served CLONE:  ts_http_pv2_19.py DB PORT"""
import importlib.util, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
NAMES = ('owner', 'cns')
L = {n: 'ts.pv2s19.%s.http@example.invalid' % n for n in NAMES}
pw = {u: ensure_user(u) for u in L.values()}

code = r"""
L = %r
def user(n): return env['res.users'].search([('login', '=', L[n])])
org = env['res.partner'].search([('name', '=', 'S19 http')], limit=1) or env['res.partner'].create({'name': 'S19 http', 'is_company': True})
org.write({'is_company': True})
ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create({'name': 'S19 http', 'purpose': 'education', 'partner_id': org.id})
ws.write({'approved_on': '2026-01-01 00:00:00'})
if ws.state in ('draft', 'closed'):
    ws.write({'state': 'pilot'})
for n, role in (('owner', 'owner'), ('cns', 'counselor')):
    u = user(n)
    m = env['ts.workspace.member'].search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)]) or env['ts.workspace.member'].create(
        {'workspace_id': ws.id, 'user_id': u.id, 'role': role})
    if m.role != role:
        m.write({'role': role})
env.cr.commit()
print('WS', ws.id)
""" % L
out = shell(code)
mm = re.search(r'WS (\d+)', out)
assert mm, out[-1200:]
WS = mm.group(1)
W = '/my/workspaces/%s' % WS


def get(c, path):
    for _ in range(4):
        st, loc, body = c.req(path)
        if st in (301, 302, 303) and loc:
            path = path_of(loc)
            continue
        break
    return st, body


def login(n):
    c = Client(TS)
    assert c.login(L[n], pw[L[n]]), n
    return c


FORBIDDEN = ('رشتهٔ مناسب تو', 'رشته مناسب تو', 'احتمال قبولی', 'تضمین', 'رایگان برای همیشه')


def visible(html):
    h = re.sub(r'(?is)<(script|style|bdi|code|svg|noscript)\b.*?</\1>', ' ', html)
    h = re.sub(r'(?is)<head\b.*?</head>', ' ', h)
    h = re.sub(r'(?s)<[^>]+>', ' ', h)
    return re.sub(r'\s+', ' ', h)


def scan(path, html):
    """-> list of problems found on one rendered page."""
    bad = []
    if not re.search(r'(?is)<h1\b', html):
        bad.append('no h1')
    t = re.search(r'(?is)<title[^>]*>(.*?)</title>', html)
    if not t or not re.search(r'[؀-ۿ]', t.group(1)):
        bad.append('title not Persian')
    for w in FORBIDDEN:
        if w in html:
            bad.append('forbidden: %s' % w)
    eng = re.findall(r'(?<![\w/#.@-])[A-Za-z]{4,}(?![\w/@.-])', visible(html))
    eng = [w for w in eng if w.lower() not in ('http', 'https', 'www', 'csv', 'xlsx', 'json', 'webp', 'png', 'jpg', 'jpeg', 'pdf', 'zip')]      # file-format names are codes
    if eng:
        bad.append('English: %s' % ','.join(sorted(set(eng))[:6]))
    labels = ' '.join(re.findall(r'(?is)<label\b[^>]*>.*?</label>', html))
    fors = set(re.findall(r'(?is)<label\b[^>]*\bfor="([^"]+)"', html))
    for m in re.finditer(r'(?is)<(input|select|textarea)\b([^>]*)>', html):
        a = m.group(2)
        ty = re.search(r'type="([^"]+)"', a)
        if m.group(1).lower() == 'input' and ty and ty.group(1) in ('hidden', 'submit', 'button', 'image', 'reset'):
            continue
        if 'aria-label' in a or 'aria-labelledby' in a:
            continue
        i = re.search(r'\bid="([^"]+)"', a)
        if i and i.group(1) in fors:
            continue
        nm = re.search(r'\bname="([^"]+)"', a)
        if nm and re.search(r'<(input|select|textarea)\b[^>]*name="%s"' % re.escape(nm.group(1)), labels):
            continue
        bad.append('unlabelled field %s' % (nm.group(1) if nm else a[:30]))
    if re.search(r'(?is)<img\b(?![^>]*\balt=)[^>]*>', html):
        bad.append('img without alt')
    return bad


# ---- help center
st, page = get(Client(TS), '/help/panel')
check('the help center opens without signing in', st == 200 and 'راهنمای پنل' in page, st)
ids = ('invite', 'import', 'report', 'roles', 'sharing', 'minors', 'export', 'support', 'credits')
check('every help section has its anchor', all('id="%s"' % i in page for i in ids), [i for i in ids if 'id="%s"' % i not in page])
check('the help center names the date it was checked', 'آخرین بررسی' in page and '۱۴۰۵' in page)
check('the public help page links to support without a panel number', 'href="/contact?topic=panel"' in page)

ow = login('owner')
st, page = get(ow, '/help/panel')
check('a member gets the support link with the panel number', 'href="/contact?topic=panel&amp;panel=%s"' % WS in page or
      'href="/contact?topic=panel&panel=%s"' % WS in page, st)
st, page = get(ow, W)
check('the menu help link points to the help center', 'href="/help/panel"' in page, st)

# ---- contextual help links
st, page = get(ow, W + '/exports')
check('the export page has a "what is this" link', 'href="/help/panel#export"' in page, st)
st, page = get(ow, W + '/audit')
check('the audit page has a "what is this" link', 'href="/help/panel#support"' in page, st)
st, page = get(ow, '/my/sharing')
check('the sharing page has a "what is this" link', 'href="/help/panel#sharing"' in page, st)

# ---- scan of every route: Persian only, one h1, labelled fields, no forbidden claim
ROUTES = ['', '/clients', '/invites', '/campaigns', '/groups', '/members', '/reports', '/credits', '/notifications',
          '/audit', '/settings', '/exports', '/import']
OTHER = ['/help/panel', '/help/roles', '/my', '/my/account', '/my/sharing', '/my/privacy']
for who in ('owner', 'cns'):
    c = ow if who == 'owner' else login('cns')
    seen = 0
    for r in [W + x for x in ROUTES] + OTHER:
        st, html = get(c, r)
        if st != 200:
            continue
        seen += 1
        bad = scan(r, html)
        check('%s: %s passes the text and accessibility scan' % (who, r.replace(W, 'W')), not bad, '; '.join(bad)[:300])
    check('%s: at least 8 pages were scanned' % who, seen >= 8, seen)

summary()
