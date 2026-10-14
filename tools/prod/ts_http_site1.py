#!/usr/bin/env python3
"""site1 over HTTP against a served CLONE: talentsearch.ir is one page. The hero is the free career test (mobile sign-in
first, /career/start -> /signup), then the organisation panel (#orgs with #clinics #hiring #schools), science, privacy,
pricing, questions and contact (the shared lead form posts /ts/lead). The menu links the sections; the retired pages
301 to them; /contact (form errors, a panel's top-up request) and /privacy stay; eot.ir is untouched.
    ts_http_site1.py DB PORT"""
import importlib.util, os, re, sys

DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, summary = lib.Client, lib.check, lib.summary


def csrf(page):
    m = re.search(r'name="csrf_token" value=["\']([^"\']+)', page)     # Odoo 20 may quote this value with '
    return m.group(1) if m else ''

TS, EOT = 'talentsearch.ir', 'eot.ir'

anon = Client(TS)
st, loc, home = anon.req('/')
check('S01 / is 200 with one h1, the career question', st == 200 and home.count('<h1') == 1 and 'چه شغل‌هایی با علایق شما متناسب است؟' in home, str(st))
hero = home.split('id="career"', 1)[1].split('</section>', 1)[0] if 'id="career"' in home else ''
check('S02 the hero: one primary «شروع آزمون رایگان» to /career/start, a quiet link to #orgs, the sign-in note',
      hero.count('ts-btn--primary') == 1 and re.search(r'href="/career/start"[^>]*id="ts-hero-career"', hero)
      and 'شروع آزمون رایگان' in hero and 'href="#orgs"' in hero and 'id="ts-hero-hint"' in hero
      and 'حدود ۸ دقیقه' in hero and 'نتیجه را فقط خودتان می‌بینید' in hero, hero[:120])
check('S03 the hero preview is decorative and labelled «نمونه»', 'ts-cmock' in hero and 'aria-hidden="true"' in hero and 'نمونه' in hero)
for sid in ('career', 'how', 'orgs', 'clinics', 'hiring', 'schools', 'science', 'privacy', 'pricing', 'faq', 'contact'):
    check('S04 section #%s exists once' % sid, home.count('id="%s"' % sid) == 1)
order = [home.index('id="%s"' % s) for s in ('career', 'orgs', 'science', 'pricing', 'faq', 'contact') if ('id="%s"' % s) in home]
check('S05 sections in order: career, orgs, science, pricing, faq, contact', len(order) == 6 and order == sorted(order))
nav = re.search(r'<ul class="ts-dnav__list top_menu">(.*?)</ul>', home, re.S)
nav = nav.group(1) if nav else ''
check('S06 the menu links the sections', all(('href="/#%s"' % s) in nav for s in ('career', 'orgs', 'science', 'pricing', 'contact'))
      and '/schools' not in nav and '/pricing"' not in nav, nav[:160])
orgs = home.split('id="orgs"', 1)[1].split('</section>', 1)[0] if 'id="orgs"' in home else ''
check('S07 #orgs: a build link per kind (clinic, solo, org, school), the samples, the free panel and the demo request',
      all(('href="/panel?kind=%s"' % k) in orgs for k in ('clinic', 'solo', 'org', 'school'))
      and all(('href="/sample/%s"' % k) in orgs for k in ('clinic', 'hr', 'school')) and 'href="/panel"' in orgs and 'href="#contact"' in orgs)
sci = home.split('id="science"', 1)[1].split('</section>', 1)[0] if 'id="science"' in home else ''
check('S08 #science: the O*NET notice (CC BY 4.0) and the scientific lead', 'CC BY 4.0' in sci and 'USDOL/ETA' in sci
      and 'دکتر ناصرالدین کاظمی حقیقی' in sci and 'dr-kazemi.webp' not in sci)
check('S09 #faq: eight closed questions', home.count('class="ts-faq__item"') == 8 and home.count('aria-expanded="false"') >= 8)
con = home.split('id="contact"', 1)[1].split('</section>', 1)[0] if 'id="contact"' in home else ''
check('S10 #contact: the lead form (csrf, consent box) and the other ways', 'action="/ts/lead"' in con and 'name="csrf_token"' in con
      and 'name="consent_contact"' in con and 'info@eot.ir' in con and '۱۲۳' in con)
check('S11 the meta description; the one Odoo Organization JSON-LD (no second one)', home.count('"@type": "Organization"') == 1
      and re.search(r'<meta name="description" content="آزمون شغلی رایگان', home) is not None)
check('S12 no retired targets left on the home', not re.search(r'href="/(schools|pricing|clinics|hiring)(["#?])', home))

# the career start keeps mobile sign-in first (owner 2026-10-14)
st, loc, _ = anon.req('/career/start')
check('S13 /career/start (public) -> mobile sign-in first', st in (302, 303) and ('/signup' in loc or loc.endswith('/career')), '%s %s' % (st, loc))

# the lead form from the home
st, loc, _ = anon.req('/ts/lead', {'csrf_token': csrf(home), 'topic': 'question', 'name': 'آزمون site1',
                                     'contact': 'site1@example.invalid', 'message': 'site1', 'consent_contact': '1'})
check('S14 the home form creates a lead -> /contact/thanks', st in (302, 303) and loc.endswith('/contact/thanks'), '%s %s' % (st, loc))
st, loc, _ = anon.req('/ts/lead', {'csrf_token': csrf(home), 'topic': 'question', 'name': ''})
check('S15 an incomplete form returns to /contact with the error', st in (302, 303) and '/contact?topic=question&error=1' in loc, loc)
st, _, pg = anon.req('/contact?topic=credit&panel=TS-ABC')
check('S16 /contact stays: the top-up request names the panel', st == 200 and 'name="panel" value="TS-ABC"' in pg and 'کد پنل: TS-ABC' in pg
      and 'value="credit" selected' in pg.replace('selected="selected"', 'selected'), str(st))

# redirects
for old, new in (('/schools', '/#schools'), ('/pricing', '/#pricing'), ('/clinics', '/#clinics'), ('/hiring', '/#hiring'),
                 ('/employers', '/#hiring'), ('/help', '/#faq'), ('/how-it-works', '/#orgs')):
    st, loc, _ = anon.req(old)
    check('S17 %s -> %s (301)' % (old, new), st == 301 and loc.endswith(new), '%s %s' % (st, loc))
for p in ('/privacy', '/assessments', '/career', '/contact/thanks', '/sample/clinic', '/panel'):
    st, _, _ = anon.req(p)
    check('S18 %s still 200' % p, st == 200, str(st))

# eot.ir: none of this
e = Client(EOT)
st, _, eh = e.req('/')
check('S19 eot.ir home is not the Talent Search page', st == 200 and 'ts-one' not in eh and 'چه شغل‌هایی با علایق شما' not in eh, str(st))
check('S20 eot.ir has no /career, /clinics redirect stays theirs', e.req('/career')[0] == 404 and e.req('/clinics')[0] in (404, 301, 302))
summary()
