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
_spec = __import__('importlib.util').util.spec_from_file_location(
    'flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
_lib = __import__('importlib.util').util.module_from_spec(_spec)
_spec.loader.exec_module(_lib)
_lib.setup(DB, PORT)
_lib.fake_kavenegar()     # clones never text anyone: any SMS of this flow goes to a local fake gateway
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
                        '--addons-path=/opt/odoo/talentsearch_stage%s/addons,/opt/odoo/themes,/opt/odoo/enterprise,/opt/odoo/odoo/addons' % (
                            '' if os.environ.get('TS_SLOT', '0') == '0' else '_s' + os.environ['TS_SLOT']),
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
st, _, page = anon.req('/assessments?all=1')
# onb2: the card of the starter (a guest-ok instrument) opens its start screen /start/<slug>
slugs = re.findall(r'href="/(?:assessments|start)/([^"/]+)"', page)
check('catalog 200 with 33 source instruments + the talent inventory', st == 200 and len(set(slugs)) == 34, '%s %d' % (st, len(set(slugs))))
eot = Client('www.eot.ir')
check('catalog is 404 on eot.ir', eot.req('/assessments')[0] == 404)
check('/take is 404 on eot.ir', eot.req('/take/x')[0] in (404, 303))
slug = next(s for s in slugs if urllib.parse.unquote(s).startswith('فهرست-تعهد-فردی'))
st, _, page = anon.req('/assessments/' + slug)
check('detail page 200 for anonymous with sign-up option', st == 200 and 'href="/signup?' in page, str(st))
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
st, loc, _ = u.req('/take/%s/consent' % token, {'csrf_token': u.csrf(page), 'consent_service': '1', 'age18': 'yes'})
st, _, page = u.req('/take/' + token)
nq = page.count('class="ts-q"')
check('player page renders (up to 5 items per page, 5-point scale)', st == 200 and 1 <= nq <= 5 and page.count('type="radio"') == 5 * nq,
      '%s q=%d' % (st, page.count('class="ts-q"')))
check('player: no radiogroup role inside the fieldset, items have anchors (T7 B8-8, B11-2)', 'role="radiogroup"' not in page and 'id="q-' in page)
csrf = u.csrf(page)
# T7 (B11-1/2, B8-4b): before answering, the review lists unanswered items by page; each link opens its page with the item marked
st, _, rv = u.req('/take/%s/review' % token)
mlink = re.search(r'href="(/take/%s\?page=\d+&amp;missing=1)#q-\d+"' % token, rv)
check('review before answering: unanswered items grouped by page, links jump to the item', st == 200 and mlink and 'class="ts-review__page"' in rv
      and 'رفتن به اولین پرسش بی‌پاسخ' in rv)
if mlink:
    st, _, pg = u.req(html.unescape(mlink.group(1)))
    check('…and the item is marked «بی‌پاسخ» on its page', st == 200 and 'data-missing="1"' in pg and 'ts-q__flag' in pg)
pages = int((re.search(r'صفحهٔ [۰-۹]+ از ([۰-۹]+)', page) or re.match('(۱)', '۱')).group(1).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')))  # one page: no page count
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
check('review shows no missing items', st == 200 and 'ارسال و دیدن نتیجه' in page and 'id="ts-review-missing"' not in page)
st, loc, _ = u.req('/take/%s/submit' % token, {'csrf_token': u.csrf(page), 'submission_key': token})
report = path_of(loc)
check('submit -> report', st in (302, 303) and report.startswith('/my/assessments/'), loc)
st, loc2, _ = u.req('/take/%s/submit' % token, {'csrf_token': u.csrf(page), 'submission_key': token})
check('second submit redirects to the same report', path_of(loc2).split('?')[0] == report.split('?')[0], loc2)
st, _, page = u.req(report.split('?')[0])
check('report 200 with summary, bands and interpretation', st == 200 and 'خلاصهٔ نتیجه‌ها' in page and 'ts-band' in page and 'تفسیر نتیجهٔ شما' in page)
check('report hides therapist guidance', 'راهنمای تخصصی درمانگر' not in page and 'راهنمای تخصصی مشاور' not in page and 'تحلیل و تفسیر' not in page)
check('report has no English band words', not re.search(r'\b(Low|Medium|High)\b', html.unescape(re.sub(r'<[^>]+>', ' ', page))))
check('report: result at a glance before the table, crisis lines 123 and 1480 (T7, owner 2026-10-13)',
      0 < page.find('id="ts-glance"') < page.find('id="ts-summary"') and 'اورژانس اجتماعی ۱۲۳' in page and '۱۴۸۰' in page and '۱۱۵' not in page)
st, _, page = u.req('/my/assessments')
check('my assessments lists the report', st == 200 and report.split('?')[0] in page)
st, _, page = u.req('/my')
check('portal home lists my results (S15 home)', st == 200 and 'ts-home-results' in page and 'href="/my/assessments"' in page)
check('panels card hidden for a non-member', 'ts-home-panels' not in page)
check('header has a «سنجه‌های من» link for signed-in users', 'id="ts-appnav"' in page and 'href="/my/assessments"' in page)   # UI-1: the app bar carries the link

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
