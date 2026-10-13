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
TS = 'talentsearch.ir'
LOGIN = 'ts.talent.http@example.invalid'

anon = Client(TS)
st, _, page = anon.req('/assessments')
check('/assessments is the talent inventory page with the sample matrix', st == 200 and 'فهرست تعاملی استعداد' in page and 'برجسته' in page and 'نزدیک' in page and 'id="sample"' in page)
st, _, page = anon.req('/assessments?all=1')
m = re.search(r'href="/assessments/([^"/]*استعداد[^"/]*)"', page)
check('the full catalog lists the talent inventory', st == 200 and bool(m) and 'جمله برای هر زمینه' in page)
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
check('consent page header says «خروج» (nothing to save there), not «ذخیره و خروج»',
      re.search(r'id="ts-focus-exit"[^>]*>بازگشت به فهرست</a>', page) is not None and 'ذخیره و خروج' not in page)
check('consent states the whole effort and folds the practical details behind one button',
      '۶ تا ۱۰ دقیقه' in page and 'data-tt-fold' in page and 'aria-controls="tt-consent-more"' in page and 'id="tt-who-sees"' in page)
st, loc, _ = u.req('/take/%s/consent' % token, {'csrf_token': u.csrf(page)})
check('consent without the box refused', 'error=consent' in loc, loc)
# T7 integrator (B handoff): one error summary under the H1, and the age answer posted before the refusal comes back ticked
st, loc, _ = u.req('/take/%s/consent' % token, {'csrf_token': u.csrf(page), 'age18': 'yes'})
st, _, ep = u.req(path_of(loc))
check('the refusal shows one error summary and keeps the posted age answer ticked',
      'error=consent' in loc and 'age=yes' in loc and 'id="ts-error-summary"' in ep and 'href="#tt-consent-service"' in ep
      and re.search(r'id="ts-age-yes"[^>]*checked', ep) is not None, loc)
# verify T7: the consent error sits next to its checkbox (age box first), and an age error is named in the summary
check('the consent error sits between the age box and its checkbox',
      'id="ts-age-box"' in ep and 'id="tt-err-consent"' in ep
      and ep.index('id="ts-age-box"') < ep.index('id="tt-err-consent"') < ep.index('id="tt-consent-service"'))
st, _, ap = u.req('/take/%s?error=age&svc=1' % token)
check('an age error is listed in the error summary (never an empty summary)',
      st == 200 and 'id="ts-error-summary"' in ap and 'href="#ts-age-yes"' in ap, st)
u.req('/take/%s/consent' % token, {'csrf_token': u.csrf(page), 'consent_service': '1', 'age18': 'yes'})
st, _, page = u.req('/take/' + token)
check('name step shown after consent', st == 200 and 'name="label"' in page and 'tt-input' in page)
check('name step: plain counter, the 2-8 range only in the journey line', 'زمینهٔ ۱<' in page and '(۲ تا ۸)' not in page and 'معمولاً ۳ تا ۵ زمینه' in page)
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
            st, _, mp = u.req(path_of(loc))
            check('missing statements: summary links to each one, marked with a word (not colour only), aria-invalid',
                  'id="tt-error-summary"' in mp and 'href="#q-' in mp and mp.count('class="tt-miss"') == 5 and 'aria-invalid="true"' in mp)
        for i in ids:
            data['c_' + i] = value_of(seen)
            seen += 1
        st, loc, _ = u.req('/take/%s/mpage' % token, data)
    return loc


loc = take_field('ریاضی', lambda k: str(1 + k % 5))
check('field 1 done -> between screen', 'v=straight' not in loc)
st, _, page = u.req('/take/' + token)
check('between screen (below minimum): the field is listed, adding is the primary action, no finish form yet',
      'ریاضی' in page and 'tt-btn tt-btn--primary tt-btn--block' in page and 'tt-finish' not in page and 'زمینه‌های کامل‌شده' in page)
st, loc, _ = u.req('/take/%s/finish' % token, {'csrf_token': u.csrf(page)})
check('finish with one field refused', '/my/assessments' not in loc, loc)
st, _, page = u.req(path_of(loc))
check('the refusal says why, as an error on top', 'class="tt-error"' in page and 'هنوز نمی‌شود پایان را زد' in page)
loc = take_field('فارسی', lambda k: '3')
check('all-equal answers -> confirmation screen', 'v=straight' in loc, loc)
st, _, page = u.req(path_of(loc))
check('straight screen: reason given, reviewing is the primary action', st == 200 and 'بازبینی پاسخ‌ها' in page
      and 'پنج توانایی متفاوت' in page and bool(re.search(r'class="tt-btn tt-btn--primary"[^>]*>بازبینی', page)) and 'زمینهٔ ۲<' in page)
st, loc, _ = u.req('/take/%s/mpage' % token, {'csrf_token': u.csrf(page), 'p': 3, 'go': 'done', 'confirm': '1'})
st, _, page = u.req('/take/' + token)
check('two fields: the 3-5 advice stays, adding a field is still primary and finishing is offered as the second action',
      'معمولاً ۳ تا ۵ زمینه' in page and 'tt-btn tt-btn--primary tt-btn--block' in page and 'tt-finish' in page
      and bool(re.search(r'class="tt-btn tt-btn--ghost"[^>]*>پایان و دیدن نتیجه', page)))
# verify T7: after a failed finish, finishing is the primary action, the error sits above it, no «✓ … کامل شد»
st, _, fp = u.req('/take/%s?error=finish' % token)
check('a failed finish makes «پایان» primary, keeps the error next to it and drops the ✓ heading',
      st == 200 and bool(re.search(r'class="tt-btn tt-btn--primary"[^>]*>پایان و دیدن نتیجه', fp)) and 'id="tt-err-finish"' in fp
      and 'پایان هنوز ثبت نشده است' in fp and 'tt-badge' not in fp and 'با پشتیبانی تماس بگیر' in fp, st)
loc = take_field('هنر', lambda k: str(5 - k % 5))
st, _, page = u.req('/take/' + token)
st, loc, _ = u.req('/take/%s/finish' % token, {'csrf_token': u.csrf(page)})
check('finish -> own report', st in (302, 303) and '/my/assessments/' in loc and 'submitted=1' in loc, loc)
report = path_of(loc)
st, _, page = u.req(report)
check('report renders 3 fields, tiles, 7 levels and table', st == 200 and 'tt-tiles' in page and page.count('tt-panel"') >= 3
      and page.count('<h3>') >= 7 and 'tt-table' in page)
check('report has the fields-side-by-side section', 'tt-compare' in page and page.count('tt-cmp__row') == 6 and 'برجسته' in page)
check('report: the plain summary comes before the metadata (first phone screen)',
      'id="tt-sec-summary"' in page and 'ts-doc__meta' in page and page.index('id="tt-sec-summary"') < page.index('ts-doc__meta'))
check('participant report is not in org mode', 'tt-cobrand' not in page)
check('report shows program names from the book', 'غنی‌سازی' in page or 'تسریعی' in page)
check('full tie (all fields 60): stated once, no arbitrary weakest field or remedial program', 'همهٔ زمینه‌ها برابر' in page and 'پایین‌ترین زمینه' not in page and 'آموزش جبرانی' not in page)
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
st, _, page = anon.req('/entekhab-reshteh')
check('retired landing 301s to /assessments', st == 301)
st, _, page = anon.req('/entekhab-reshteh/sample')
check('retired sample 301s to /assessments', st == 301)
check('landing and sample are 404 on eot.ir', Client('www.eot.ir').req('/entekhab-reshteh')[0] == 404 and Client('www.eot.ir').req('/entekhab-reshteh/sample')[0] == 404)
check('org person route needs login', anon.req('/my/workspaces/1/p/1')[0] in (303, 302, 404))
summary()
