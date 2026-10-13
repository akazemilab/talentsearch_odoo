#!/usr/bin/env python3
"""konkur - deterministic data tools for the konkur major-fit product (run as `ts konkur SUB ...`).

Data root /root/share/konkur (raw/ PDFs, work/ extracted CSVs, out/ profiles, reports/). Reference tables live in the
repo (tools/konkur/ref) so every mapping decision is versioned. Every command prints a short verdict, never page dumps
(peek prints at most 60 lines of one page, on purpose).

  doctor                          PDF backends, python, data dirs, O*NET cache shape
  status                          raw files (MB, pages), work/out files, reference table sizes
  fetch KIND URL [NAME]           download (https, allow-listed Iranian education hosts) into raw/KIND; KIND booklet|curriculum|ref
  import KIND NAME                move /root/share/in/konkur/NAME into raw/KIND
  peek KIND/FILE PAGE [N]         cleaned text lines of one page (max 60) to design a parse rule
  find KIND/FILE REGEX [MAX]      pages whose cleaned text matches REGEX (first hit per page)
  booklet KIND/FILE GROUP         coded rows -> work/booklet_GROUP.csv          (long: ts konkur bg NAME booklet ...)
  majors                          booklet rows + rule -> work/majors.csv, unmapped vs ref/major_family.csv
  curriculum KIND/FILE FAMILY     course-like rows -> work/curriculum/FAMILY.csv
  courses [FAMILY]                curriculum rows + rule -> work/courses/FAMILY.csv
  classify                        courses -> knowledge areas; reports/unclassified_courses.csv
  onet-find WORDS...              O*NET occupations by Persian/English title words (for ref/family_onet.csv)
  build                           out/major_profiles.json (+ reports/profile_issues.txt)
  match STUDENT.json|--demo [TOP] ranked families for one student (engine KK-MATCH)
  test                            golden tests (no data needed)
"""
import csv
import glob
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kk_extract  # noqa: E402
import kk_match  # noqa: E402
import kk_pdf  # noqa: E402
import kk_profile  # noqa: E402
from kk_text import key, norm  # noqa: E402

D = os.environ.get('KK_DATA', '/root/share/konkur')
INBOX = '/root/share/in/konkur'
ONET_CACHE = os.environ.get('KK_ONET', '/root/onet-match/out/m4/onet_cache_v1.json')
ONET_FA = '/root/talentsearch_odoo/addons/ts_onet/data/onet_hr.json'
REF = kk_profile.REF
KINDS = ('booklet', 'curriculum', 'ref')
HOSTS = ('sanjesh.org', 'msrt.ir', 'ac.ir', 'behdasht.gov.ir', 'sccr.ir', 'medu.ir', 'irphe.ac.ir', 'nces.ed.gov',
         'onetcenter.org')
MAX_MB = 400


def say(ok, head, lines=()):
    print('KONKUR %s' % head + ('' if ok else '  [FAIL]'))
    for ln in list(lines)[:40]:
        print('  ' + str(ln)[:200])
    return 0 if ok else 1


def inside(path):
    real = os.path.realpath(path)
    if not real.startswith(os.path.realpath(D) + '/'):
        raise SystemExit('KONKUR refused: %s is outside %s' % (path, D))
    return real


def raw(rel):
    p = inside(os.path.join(D, 'raw', rel))
    if not os.path.exists(p):
        raise SystemExit('KONKUR missing: raw/%s (see `ts konkur status`)' % rel)
    return p


def dirs():
    for sub in ('raw/booklet', 'raw/curriculum', 'raw/ref', 'work/curriculum', 'work/courses', 'out', 'reports'):
        os.makedirs(os.path.join(D, sub), exist_ok=True)


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def manifest(kind, name, src):
    p = os.path.join(D, 'raw', 'MANIFEST.tsv')
    f = os.path.join(D, 'raw', kind, name)
    with open(p, 'a', encoding='utf-8') as m:
        m.write('%s\t%s/%s\t%s\t%s\t%s\n' % (time.strftime('%Y-%m-%d %H:%M'), kind, name, kk_pdf.size_mb(f), sha(f)[:16], src))


# ---------------------------------------------------------------- commands
def c_doctor(a):
    dirs()
    lines = ['python %s' % sys.version.split()[0], 'pdf backends: %s' % (', '.join(kk_pdf.backends()) or 'NONE'),
             'data %s (free %.1f GB)' % (D, shutil.disk_usage(D).free / 1e9)]
    if os.path.exists(ONET_CACHE):
        with open(ONET_CACHE, encoding='utf-8') as f:
            c = json.load(f)
        top = list(c)[:12] if isinstance(c, dict) else type(c).__name__
        lines.append('onet cache %s: top keys %s' % (os.path.basename(ONET_CACHE), top))
        occ = c.get('occupations') if isinstance(c, dict) else None
        if isinstance(occ, dict) and occ:
            k0 = sorted(occ)[0]
            o = occ[k0]
            lines.append('occupations %d; %s keys %s' % (len(occ), k0, sorted(o)[:20] if isinstance(o, dict) else type(o).__name__))
            for fld in ('OI', 'oi', 'interests', 'riasec', 'EX', 'values', 'KN', 'knowledge'):
                if isinstance(o, dict) and fld in o:
                    v = o[fld]
                    lines.append('  %s: %s' % (fld, (sorted(v)[:8] if isinstance(v, dict) else str(v)[:80])))
    else:
        lines.append('onet cache MISSING at %s' % ONET_CACHE)
    lines.append('ts_onet persian titles: %s' % ('ok' if os.path.exists(ONET_FA) else 'missing'))
    ok = bool(kk_pdf.backends())
    return say(ok, 'doctor', lines)


def c_status(a):
    dirs()
    lines = []
    for kind in KINDS:
        for f in sorted(glob.glob(os.path.join(D, 'raw', kind, '*'))):
            try:
                pages = kk_pdf.page_count(f) if f.lower().endswith('.pdf') else '-'
            except Exception as e:
                pages = 'err:%s' % e.__class__.__name__
            lines.append('raw/%s/%s  %s MB  pages %s' % (kind, os.path.basename(f), kk_pdf.size_mb(f), pages))
    for f in sorted(glob.glob(os.path.join(D, 'work', '**', '*.csv'), recursive=True)) + sorted(glob.glob(os.path.join(D, 'out', '*'))):
        n = sum(1 for _ in open(f, encoding='utf-8')) - 1 if f.endswith('.csv') else '-'
        lines.append('%s  rows %s' % (os.path.relpath(f, D), n))
    for f in sorted(glob.glob(os.path.join(REF, '*'))):
        n = sum(1 for _ in open(f, encoding='utf-8')) - 1 if f.endswith('.csv') else '-'
        lines.append('ref/%s  rows %s' % (os.path.basename(f), n))
    return say(True, 'status (%d items)' % len(lines), lines)


def c_fetch(a):
    if len(a) < 2 or a[0] not in KINDS:
        return say(False, 'fetch KIND URL [NAME]: KIND in %s' % (KINDS,))
    kind, url = a[0], a[1]
    u = urllib.parse.urlparse(url)
    host = (u.hostname or '').lower()
    if u.scheme != 'https' or not any(host == h or host.endswith('.' + h) for h in HOSTS):
        return say(False, 'fetch refused: https only, hosts %s' % (HOSTS,))
    name = re.sub(r'[^\w.\-]', '_', a[2] if len(a) > 2 else (os.path.basename(u.path) or 'file'))[:120]
    dirs()
    dst = os.path.join(D, 'raw', kind, name)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (konkur-tools)'})
    t0, n = time.time(), 0
    with urllib.request.urlopen(req, timeout=60) as r, open(dst + '.part', 'wb') as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            n += len(b)
            if n > MAX_MB * 1048576:
                f.close()
                os.remove(dst + '.part')
                return say(False, 'fetch: larger than %d MB, stopped' % MAX_MB)
            f.write(b)
    os.replace(dst + '.part', dst)
    manifest(kind, name, url)
    pages = kk_pdf.page_count(dst) if dst.lower().endswith('.pdf') else '-'
    return say(True, 'fetch raw/%s/%s: %s MB, pages %s, %.0f s' % (kind, name, kk_pdf.size_mb(dst), pages, time.time() - t0))


def c_import(a):
    if len(a) < 2 or a[0] not in KINDS:
        return say(False, 'import KIND NAME')
    src = os.path.realpath(os.path.join(INBOX, a[1]))
    if not src.startswith(INBOX + '/') or not os.path.isfile(src):
        return say(False, 'import: %s not found in %s' % (a[1], INBOX))
    dirs()
    name = re.sub(r'[^\w.\-]', '_', os.path.basename(src))[:120]
    shutil.move(src, os.path.join(D, 'raw', a[0], name))
    manifest(a[0], name, 'inbox:' + a[1])
    return say(True, 'import raw/%s/%s' % (a[0], name))


def c_peek(a):
    f, page, n = raw(a[0]), int(a[1]), min(60, int(a[2]) if len(a) > 2 else 40)
    text = kk_pdf.pages_text(f, page, page)[0]
    lines = [kk_extract.clean_line(x) for x in text.splitlines() if x.strip()]
    return say(True, 'peek %s p%d: %d lines (showing %d)' % (a[0], page, len(lines), min(n, len(lines))), lines[:n])


def c_find(a):
    f, rx, mx = raw(a[0]), re.compile(a[1]), int(a[2]) if len(a) > 2 else 20
    hits = []
    for page, text in kk_pdf.iter_pages(f):
        for ln in text.splitlines():
            c = kk_extract.clean_line(ln)
            if rx.search(c):
                hits.append('p%d: %s' % (page, c))
                break
        if len(hits) >= mx:
            break
    return say(True, 'find %s /%s/: %d pages' % (a[0], a[1], len(hits)), hits)


def c_booklet(a):
    rows, pages, coded = kk_extract.booklet_rows(raw(a[0]), a[1])
    out = os.path.join(D, 'work', 'booklet_%s.csv' % a[1])
    kk_extract.write_csv(rows, out, ['group', 'page', 'code', 'line'])
    codes = len({r['code'] for r in rows})
    return say(bool(rows), 'booklet %s -> %s: %d pages, %d with codes, %d rows, %d distinct codes' % (
        a[0], os.path.relpath(out, D), pages, coded, len(rows), codes))


def c_majors(a):
    rule = kk_extract.rules().get('booklet', {})
    rx = re.compile(rule['name_rx']) if rule.get('name_rx') else None
    if not rx:
        return say(False, 'majors: set booklet.name_rx in ref/parse_rules.json after `peek` (no rule yet)')
    majors, miss = {}, 0
    for f in sorted(glob.glob(os.path.join(D, 'work', 'booklet_*.csv'))):
        for r in csv.DictReader(open(f, encoding='utf-8')):
            m = rx.search(r['line'])
            if not m:
                miss += 1
                continue
            name = norm(m.group('name'))
            k = (r['group'], key(name))
            majors.setdefault(k, {'group': r['group'], 'major': name, 'key': key(name), 'codes': 0})['codes'] += 1
    rows = sorted(majors.values(), key=lambda r: (r['group'], -r['codes'], r['key']))
    kk_extract.write_csv(rows, os.path.join(D, 'work', 'majors.csv'), ['group', 'major', 'key', 'codes'])
    mapped = {key(r['major']) for r in kk_profile.read_csv(os.path.join(REF, 'major_family.csv'))}
    un = [r for r in rows if r['key'] not in mapped]
    return say(True, 'majors: %d distinct (group, major), %d rows without a name match, %d not yet in ref/major_family.csv' % (
        len(rows), miss, len(un)), ['%s | %s | %d codes' % (r['group'], r['major'], r['codes']) for r in un[:15]])


def c_curriculum(a):
    rows, pages = kk_extract.curriculum_rows(raw(a[0]), a[1])
    out = os.path.join(D, 'work', 'curriculum', '%s.csv' % a[1])
    kk_extract.write_csv(rows, out, ['family_id', 'page', 'name', 'numbers', 'line'])
    return say(bool(rows), 'curriculum %s -> %s: %d pages, %d course-like rows' % (a[0], os.path.relpath(out, D), pages, len(rows)))


def c_courses(a):
    rule = kk_extract.rules().get('curriculum', {})
    ti, pi, ui = rule.get('theory_index'), rule.get('practice_index'), rule.get('units_index', 0)
    files = [os.path.join(D, 'work', 'curriculum', '%s.csv' % a[0])] if a else sorted(glob.glob(os.path.join(D, 'work', 'curriculum', '*.csv')))
    lines = []
    for f in files:
        fam, out = os.path.basename(f)[:-4], []
        for r in csv.DictReader(open(f, encoding='utf-8')):
            nums = [float(x) for x in r['numbers'].split()]
            pick = lambda i: nums[i] if i is not None and -len(nums) <= i < len(nums) else 0.0  # noqa: E731
            u = pick(ui)
            if not 0 < u <= 16:
                continue
            out.append({'family_id': fam, 'course': r['name'], 'units_total': u, 'units_theory': pick(ti),
                        'units_practice': pick(pi), 'page': r['page']})
        kk_extract.write_csv(out, os.path.join(D, 'work', 'courses', fam + '.csv'),
                             ['family_id', 'course', 'units_total', 'units_theory', 'units_practice', 'page'])
        lines.append('%s: %d courses, %.0f units' % (fam, len(out), sum(x['units_total'] for x in out)))
    return say(bool(files), 'courses: %d families' % len(files), lines)


def load_courses():
    by = {}
    for f in glob.glob(os.path.join(D, 'work', 'courses', '*.csv')):
        rows = list(csv.DictReader(open(f, encoding='utf-8')))
        if rows:
            by[os.path.basename(f)[:-4]] = rows
    return by


def c_classify(a):
    clf, un, tot, gen = kk_profile.Classifier(), {}, 0, 0
    for fam, rows in sorted(load_courses().items()):
        for r in rows:
            tot += 1
            ar = clf.area(r['course'])
            if ar == 'general':
                gen += 1
            elif ar is None:
                un.setdefault(norm(r['course']), set()).add(fam)
    rows = [{'course': k, 'families': '|'.join(sorted(v)), 'area': ''} for k, v in sorted(un.items())]
    dirs()
    kk_extract.write_csv(rows, os.path.join(D, 'reports', 'unclassified_courses.csv'), ['course', 'families', 'area'])
    return say(True, 'classify: %d course rows, %d general, %d distinct unclassified -> reports/unclassified_courses.csv' % (tot, gen, len(rows)),
               [r['course'] for r in rows[:15]])


def c_onet_find(a):
    with open(ONET_FA, encoding='utf-8') as f:
        occ = json.load(f)['occupations']
    words = [key(w) for w in a]
    hits = []
    for code, o in sorted(occ.items()):
        hay = key(o.get('fa', '')) + ' ' + (o.get('en') or '').lower().replace(' ', '')
        if all(w.lower() in hay for w in words):
            hits.append('%s | %s | %s' % (code, o.get('fa'), o.get('en')))
    return say(True, 'onet-find %s: %d' % (' '.join(a), len(hits)), hits[:25])


def c_build(a):
    fams = kk_profile.read_csv(os.path.join(REF, 'families.csv'))
    if not fams:
        return say(False, 'build: ref/families.csv is empty (after `majors`, group majors into families)')
    fsoc = {r['family_id']: r['soc_codes'].split('|') for r in kk_profile.read_csv(os.path.join(REF, 'family_onet.csv'))}
    over = {}
    for r in kk_profile.read_csv(os.path.join(REF, 'family_riasec_override.csv')):
        over[r['family_id']] = {k: float(r[k]) for k in kk_match.RIASEC}
    cache = json.load(open(ONET_CACHE, encoding='utf-8')) if os.path.exists(ONET_CACHE) else None
    res = kk_profile.build(fams, load_courses(), fsoc, cache, over)
    res['inputs_hash'] = kk_profile.file_hash(glob.glob(os.path.join(REF, '*')) + glob.glob(os.path.join(D, 'work', 'courses', '*.csv')))
    dirs()
    kk_profile.dump(res, os.path.join(D, 'out', 'major_profiles.json'))
    with open(os.path.join(D, 'reports', 'profile_issues.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(res['issues']) + '\n')
    ready = sum(1 for x in res['families'] if x['riasec'] and x['subjects'])
    return say(True, 'build %s: %d families, %d complete, %d issues, inputs %s' % (
        res['version'], len(res['families']), ready, len(res['issues']), res['inputs_hash']), res['issues'][:12])


DEMO = {'group': 'tajrobi', 'riasec': {'R': 18, 'I': 34, 'A': 12, 'S': 30, 'E': 10, 'C': 16},
        'liked': {'biology': 5, 'chemistry': 4, 'math': 2, 'physics': 2},
        'grades': {'biology': 82, 'chemistry': 61, 'math': 35, 'physics': 28, 'persian': 70, 'arabic': 55}}


def c_match(a):
    p = os.path.join(D, 'out', 'major_profiles.json')
    if not os.path.exists(p):
        return say(False, 'match: run `ts konkur build` first')
    prof = json.load(open(p, encoding='utf-8'))['families']
    st = DEMO if a and a[0] == '--demo' else json.load(open(inside(os.path.join(D, a[0])), encoding='utf-8'))
    res = kk_match.match(st, [x for x in prof if x.get('riasec') or x.get('subjects')], top=int(a[1]) if len(a) > 1 else 10)
    return say(True, 'match %s: %d eligible' % (res['version'], res['n']),
               ['%5.1f  %-28s int %s sub %s  %s' % (r['fit'], (r['name'] or r['id'])[:28], r['interest'], r['subject'], ' '.join(r['reasons']))
                for r in res['rows']])


def c_test(a):
    import kk_tests
    return kk_tests.main()


CMDS = {'doctor': c_doctor, 'status': c_status, 'fetch': c_fetch, 'import': c_import, 'peek': c_peek, 'find': c_find,
        'booklet': c_booklet, 'majors': c_majors, 'curriculum': c_curriculum, 'courses': c_courses,
        'classify': c_classify, 'onet-find': c_onet_find, 'build': c_build, 'match': c_match, 'test': c_test}

if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__)
        sys.exit(2)
    try:
        sys.exit(CMDS[sys.argv[1]](sys.argv[2:]))
    except SystemExit:
        raise
    except Exception as e:
        print('KONKUR %s  [FAIL] %s: %s' % (sys.argv[1], e.__class__.__name__, str(e)[:300]))
        sys.exit(1)
