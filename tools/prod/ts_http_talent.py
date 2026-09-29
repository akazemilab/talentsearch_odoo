#!/usr/bin/env python3
"""Talent inventory over HTTP against a served CLONE:  ts_http_talent.py DB PORT
consent -> name a field -> 3 pages of statements (with the field name shown) ->
between -> two more fields -> finish -> report; plus isolation and error paths."""
import importlib.util, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, path_of, summary = lib.Client, lib.check, lib.ensure_user, lib.path_of, lib.summary
TS = 'ts.innerquest.me'
LOGIN = 'ts.talent.http@example.invalid'

anon = Client(TS)
st, _, page = anon.req('/assessments')
m = re.search(r'href="/assessments/([^"/]*استعداد[^"/]*)"', page)
check('catalog lists the talent inventory', st == 200 and bool(m) and 'جمله برای هر زمینه' in page)
slug = m.group(1) if m else ''
st, _, page = anon.req('/assessments/' + slug)
check('detail page says 15 statements per field', st == 200 and 'جمله برای هر زمینه' in page and '۵ توانایی' in page)

u = Client(TS)
check('participant login', u.login(LOGIN, ensure_user(LOGIN)))
st, _, page = u.req('/assessments/' + slug)
st, loc, _ = u.req('/assessments/%s/start' % slug, {'csrf_token': u.csrf(page)})
token = path_of(loc).split('/take/')[-1]
check('start -> /take/<token>', st in (302, 303) and len(token) == 32, loc)
st, _, page = u.req('/take/' + token)
check('consent page (matrix template)', st == 200 and 'consent_service' in page and 'tt-screen' in page)
st, loc, _ = u.req('/take/%s/consent' % token, {'csrf_token': u.csrf(page)})
check('consent without the box refused', 'error=consent' in loc, loc)
u.req('/take/%s/consent' % token, {'csrf_token': u.csrf(page), 'consent_service': '1'})
st, _, page = u.req('/take/' + token)
check('name step shown after consent', st == 200 and 'name="label"' in page and 'tt-input' in page)
st, loc, _ = u.req('/take/%s/field' % token, {'csrf_token': u.csrf(page), 'label': 'ر'})
st, _, page = u.req(path_of(loc))
check('too-short field name refused with a message', 'tt-error' in page)


def take_field(label, value_of, straight=False):
    st, _, page = u.req('/take/' + token + '?v=name')
    st, loc, _ = u.req('/take/%s/field' % token, {'csrf_token': u.csrf(page), 'label': label})
    st, _, page = u.req('/take/' + token)
    check('statements page shows the field name «%s»' % label, st == 200 and label in page and 'این زمینه' not in page)
    seen = 0
    for p in (1, 2, 3):
        st, _, page = u.req('/take/%s?p=%d' % (token, p))
        ids = re.findall(r'data-item="(\d+)"', page)
        check('page %d has 5 statements x 5 options' % p, len(ids) == 5 and page.count('type="radio"') == 25, str(len(ids)))
        data = {'csrf_token': u.csrf(page), 'p': p, 'go': 'next' if p < 3 else 'done'}
        if p == 1 and label == 'ریاضی':
            st, loc, _ = u.req('/take/%s/mpage' % token, dict(data))  # nothing answered
            check('next without answers is refused', 'error=missing' in loc, loc)
        for i in ids:
            data['c_' + i] = value_of(seen)
            seen += 1
        st, loc, _ = u.req('/take/%s/mpage' % token, data)
    return loc


loc = take_field('ریاضی', lambda k: str(1 + k % 5))
check('field 1 done -> between screen', 'v=straight' not in loc)
st, _, page = u.req('/take/' + token)
check('between screen lists the field and disables finish (below minimum)', 'ریاضی' in page and 'disabled' in page)
st, loc, _ = u.req('/take/%s/finish' % token, {'csrf_token': u.csrf(page)})
check('finish with one field refused', '/my/assessments' not in loc, loc)
loc = take_field('فارسی', lambda k: '3')
check('all-equal answers -> confirmation screen', 'v=straight' in loc, loc)
st, _, page = u.req(path_of(loc))
check('straight screen shown', st == 200 and 'مرور پاسخ‌ها' in page)
st, loc, _ = u.req('/take/%s/mpage' % token, {'csrf_token': u.csrf(page), 'p': 3, 'go': 'done', 'confirm': '1'})
loc = take_field('هنر', lambda k: str(5 - k % 5))
st, _, page = u.req('/take/' + token)
st, loc, _ = u.req('/take/%s/finish' % token, {'csrf_token': u.csrf(page)})
check('finish -> own report', st in (302, 303) and '/my/assessments/' in loc and 'submitted=1' in loc, loc)
report = path_of(loc)
st, _, page = u.req(report)
check('report renders 3 fields, tiles, 7 levels and table', st == 200 and 'tt-tiles' in page and page.count('tt-panel"') >= 3
      and page.count('<h3>') >= 7 and 'tt-table' in page)
check('report shows program names from the book', 'آموزش جبرانی' in page)
check('raw answers hidden by default behind a button', 'aria-expanded="false"' in page and 'hidden="hidden"' in page)
check('no unresolved placeholders in the report', 'None' not in page and 'False' not in page)
st, loc, _ = u.req('/take/' + token)
check('taking again after submit -> report', st in (302, 303) and '/my/assessments/' in loc)

o = Client(TS)
o.login('ts.talent.other@example.invalid', ensure_user('ts.talent.other@example.invalid'))
check("other user cannot open the attempt", o.req('/take/' + token)[0] == 404)
check("other user cannot open the report", o.req(report.split('?')[0])[0] == 404)
e = Client('www.eot.ir')
check('/take is not served on eot.ir', e.req('/take/' + token)[0] in (404, 303))
check('talent catalog is 404 on eot.ir', e.req('/assessments')[0] == 404)
summary()
