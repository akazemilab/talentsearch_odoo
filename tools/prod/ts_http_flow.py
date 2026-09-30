#!/usr/bin/env python3
"""End-to-end participant flow over HTTP against a served CLONE.
    ts_http_flow.py DB PORT
Creates two portal users on the clone (passwords stay in root-only files),
then: catalog -> detail -> start -> consent -> answer every item via the
autosave endpoint -> review -> submit (twice) -> report -> my list, plus
negative checks (other user, eot.ir host, missing consent)."""
import http.cookiejar, os, re, subprocess, sys, urllib.parse, urllib.request, html

DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
BASE = 'http://127.0.0.1:%s' % PORT
results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def ensure_user(login):
    pw_file = '/root/.ts_flow_%s_%s' % (DB, login.split('@')[0])
    if not os.path.exists(pw_file):
        pw = os.urandom(12).hex()
        old = os.umask(0o077); open(pw_file, 'w').write(pw); os.umask(old)
        code = ("u=env['res.users'].with_context(no_reset_password=True).search([('login','=','%s')])\n"
                "u=u or env['res.users'].with_context(no_reset_password=True).create({'name':'آزمون جریان','login':'%s','group_ids':[(6,0,[env.ref('base.group_portal').id])]})\n"
                "u.password=%r\nenv.cr.commit()\n") % (login, login, pw)
        subprocess.run(['sudo', '-u', 'odoo', 'env', 'HOME=/opt/odoo', '/opt/odoo/venv/bin/python3', '/opt/odoo/odoo/odoo-bin', 'shell',
                        '-c', '/etc/odoo20.conf', '-d', DB, '--db-filter=^%s$' % DB,
                        '--addons-path=/opt/odoo/talentsearch_stage/addons,/opt/odoo/themes,/opt/odoo/enterprise,/opt/odoo/odoo/addons',
                        '--no-http', '--log-level=warn'], input=code, text=True, capture_output=True, cwd='/tmp')
    return open(pw_file).read().strip()


class Client:
    def __init__(self, host):
        self.host = host
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar), NoRedirect())

    def req(self, path, data=None):
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        path = urllib.parse.quote(path, safe="/?=&%:#;,+")  # hrefs carry raw Persian slugs
        r = urllib.request.Request(BASE + path, data=body, headers={'Host': self.host, 'X-Forwarded-Proto': 'https'})
        try:
            resp = self.op.open(r, timeout=60)
            return resp.status, resp.headers.get('Location', ''), resp.read().decode('utf-8', 'ignore')
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get('Location', ''), e.read().decode('utf-8', 'ignore')

    def csrf(self, page):
        m = re.search(r'name="csrf_token" value="([^"]+)"', page)
        return m.group(1) if m else ''

    def login(self, login, pw):
        _, _, p = self.req('/web/login')
        st, loc, _ = self.req('/web/login', {'csrf_token': self.csrf(p), 'login': login, 'password': pw, 'redirect': '/my'})
        return st in (302, 303)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def path_of(loc):
    return urllib.parse.urlsplit(loc).path + (('?' + urllib.parse.urlsplit(loc).query) if urllib.parse.urlsplit(loc).query else '')


TS = 'talentsearch.ir'
anon = Client(TS)
st, _, page = anon.req('/assessments')
slugs = re.findall(r'href="/assessments/([^"/]+)"', page)
check('catalog 200 with 33 source instruments + the talent inventory', st == 200 and len(set(slugs)) == 34, '%s %d' % (st, len(set(slugs))))
eot = Client('www.eot.ir')
check('catalog is 404 on eot.ir', eot.req('/assessments')[0] == 404)
check('/take is 404 on eot.ir', eot.req('/take/x')[0] in (404, 303))
slug = next(s for s in slugs if urllib.parse.unquote(s).startswith('فهرست-تعهد-فردی'))
st, _, page = anon.req('/assessments/' + slug)
check('detail page 200 for anonymous with sign-up option', st == 200 and '/web/signup' in page, str(st))
st, loc, _ = anon.req('/assessments/%s/start' % slug, {'csrf_token': anon.csrf(page)})
check('anonymous start -> login', st in (302, 303) and '/web/login' in loc, loc)

u = Client(TS)
check('participant login', u.login('ts.flow.a@example.invalid', ensure_user('ts.flow.a@example.invalid')))
st, _, page = u.req('/assessments/' + slug)
st, loc, _ = u.req('/assessments/%s/start' % slug, {'csrf_token': u.csrf(page)})
token = path_of(loc).split('/take/')[-1]
check('start -> /take/<token>', st in (302, 303) and len(token) == 32, loc)
st, _, page = u.req('/take/' + token)
check('consent page shown first', st == 200 and 'consent_service' in page)
st, loc, _ = u.req('/take/%s/consent' % token, {'csrf_token': u.csrf(page)})
check('consent without the required box is refused', 'error=consent' in loc, loc)
st, loc, _ = u.req('/take/%s/consent' % token, {'csrf_token': u.csrf(page), 'consent_service': '1'})
st, _, page = u.req('/take/' + token)
nq = page.count('class="ts-q"')
check('player page renders (up to 10 items per page, 5-point scale)', st == 200 and 1 <= nq <= 10 and page.count('type="radio"') == 5 * nq,
      '%s q=%d' % (st, page.count('class="ts-q"')))
csrf = u.csrf(page)
pages = int(re.search(r'صفحهٔ [۰-۹]+ از ([۰-۹]+)', page).group(1).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')))
answered = 0
for p in range(1, pages + 1):
    st, _, page = u.req('/take/%s?page=%d' % (token, p))
    for iid in re.findall(r'class="ts-q" data-item="(\d+)"', page):
        st, _, body = u.req('/take/%s/answer' % token, {'csrf_token': csrf, 'item': iid, 'value': str(1 + int(iid) % 5)})
        answered += st == 200 and '"ok": true' in body.replace('"ok":true', '"ok": true')
check('every item autosaved (%d)' % answered, answered > 0)
st, _, _ = u.req('/take/%s/answer' % token, {'csrf_token': csrf, 'item': '1', 'value': '9'})
check('autosave rejects invalid value', st == 400)
st, _, page = u.req('/take/%s/review' % token)
check('review shows no missing items', st == 200 and 'ارسال نهایی' in page)
st, loc, _ = u.req('/take/%s/submit' % token, {'csrf_token': u.csrf(page), 'submission_key': token})
report = path_of(loc)
check('submit -> report', st in (302, 303) and report.startswith('/my/assessments/'), loc)
st, loc2, _ = u.req('/take/%s/submit' % token, {'csrf_token': u.csrf(page), 'submission_key': token})
check('second submit redirects to the same report', path_of(loc2).split('?')[0] == report.split('?')[0], loc2)
st, _, page = u.req(report.split('?')[0])
check('report 200 with summary, bands and interpretation', st == 200 and 'خلاصهٔ نتایج' in page and 'ts-band' in page and 'تفسیر نتیجهٔ شما' in page)
check('report hides therapist guidance', 'راهنمای تخصصی درمانگر' not in page and 'تحلیل و تفسیر' not in page)
check('report has no English band words', not re.search(r'\b(Low|Medium|High)\b', html.unescape(re.sub(r'<[^>]+>', ' ', page))))
st, _, page = u.req('/my/assessments')
check('my assessments lists the report', st == 200 and report.split('?')[0] in page)
st, _, page = u.req('/my')
m = re.search(r'<div[^>]*class="([^"]*o_portal_index_card[^"]*)"[^>]*>\s*<a[^>]*href="/my/assessments"', page)
check('portal home shows «سنجه‌های من» card VISIBLE (not d-none)', st == 200 and bool(m) and 'd-none' not in m.group(1), m.group(1) if m else 'card not found')
w = re.search(r'<div[^>]*class="([^"]*o_portal_index_card[^"]*)"[^>]*>\s*<a[^>]*href="/my/workspaces"', page)
check('workspace card hidden for a non-member', bool(w) and 'd-none' in w.group(1))
check('header has a «سنجه‌های من» link for signed-in users', page.count('href="/my/assessments" class="ts-btn ts-btn--quiet"') >= 1)

v = Client(TS)
v.login('ts.flow.b@example.invalid', ensure_user('ts.flow.b@example.invalid'))
check("other user cannot open someone else's attempt", v.req('/take/' + token)[0] == 404)
check("other user cannot open someone else's report", v.req(report.split('?')[0])[0] == 404)
e = Client('www.eot.ir')
e.login('ts.flow.a@example.invalid', ensure_user('ts.flow.a@example.invalid'))
st, _, page = e.req('/my')
check('eot.ir /my shows no Talent Search card', st == 200 and 'سنجه‌های من' not in page)
check('eot.ir /my/assessments is 404', e.req('/my/assessments')[0] == 404)
print('SUMMARY %d/%d passed' % (sum(results), len(results)))
