"""Golden tests for the konkur tools (no data, no network). `ts konkur test`."""
import kk_extract
import kk_match
import kk_profile
from kk_text import digits, key, norm

FAILS = []


def check(name, cond):
    if not cond:
        FAILS.append(name)


def main():
    # text
    check('norm arabic letters', norm('علي كريم') == 'علی کریم')
    check('persian digits', digits('کد ۱۲۳۴۵') == 'کد 12345')
    check('key ignores zwnj/space', key('زیست‌شناسی') == key('زیست شناسی') == key('زيست شناسي'))
    # classifier
    c = kk_profile.Classifier()
    for name, want in [('بیوشیمی عمومی', 'biology'), ('شیمی آلی ۲', 'chemistry'), ('مدارهای منطقی', 'computers'),
                       ('اصول فقه ۱', 'law'), ('اندیشه اسلامی ۱', 'general'), ('ریاضی عمومی ۲', 'mathematics'),
                       ('مقاومت مصالح', 'building'), ('روانشناسی رشد', 'psychology'), ('درس ناشناخته', None)]:
        check('classify %s -> %s (got %s)' % (name, want, c.area(name)), c.area(name) == want)
    know = kk_profile.read_csv(kk_profile.os.path.join(kk_profile.REF, 'knowledge.csv'))
    cp = kk_profile.course_profile([
        {'course': 'ریاضی عمومی ۱', 'units_total': 3, 'units_practice': 0},
        {'course': 'فیزیک ۱', 'units_total': 3, 'units_practice': 1},
        {'course': 'اندیشه اسلامی ۱', 'units_total': 2, 'units_practice': 0},
        {'course': 'پروژه کارشناسی', 'units_total': 3, 'units_practice': 3},
        {'course': 'درس ناشناخته', 'units_total': 1, 'units_practice': 0}], c, know)
    check('general excluded from units', cp['units_counted'] == 10)
    check('knowledge split 50/50', cp['knowledge'] == {'mathematics': 50.0, 'physics': 50.0})
    check('practice share', cp['practice_share'] == 0.4)
    check('project share', cp['project_share'] == 0.3)
    check('unclassified listed', cp['unclassified'] == ['درس ناشناخته'])
    check('subjects normalised', abs(sum(cp['subjects'].values()) - 1) < 0.01 and set(cp['subjects']) == {'math', 'physics'})
    # engine
    flat = {k: 5 for k in kk_match.RIASEC}
    check('flat person -> no interest fit', kk_match.interest_fit(flat, {'R': 1, 'I': 7, 'A': 2, 'S': 3, 'E': 4, 'C': 5}) is None)
    p = {'R': 10, 'I': 30, 'A': 5, 'S': 20, 'E': 5, 'C': 10}
    check('identical shape = 100', kk_match.interest_fit(p, p) == 100.0)
    check('opposite shape = 0', kk_match.interest_fit(p, {k: -v for k, v in p.items()}) == 0.0)
    profs = [
        {'id': 'medicine', 'name': 'پزشکی', 'groups': ['tajrobi'], 'riasec': {'R': 3, 'I': 6.5, 'A': 2, 'S': 5.5, 'E': 2.5, 'C': 3},
         'subjects': {'biology': 0.6, 'chemistry': 0.4}},
        {'id': 'civil', 'name': 'عمران', 'groups': ['riazi'], 'riasec': {'R': 6, 'I': 5, 'A': 2, 'S': 2, 'E': 3, 'C': 4},
         'subjects': {'math': 0.5, 'physics': 0.5}},
        {'id': 'psych', 'name': 'روانشناسی', 'groups': ['tajrobi', 'ensani'], 'riasec': {'R': 1.5, 'I': 5.5, 'A': 3, 'S': 6.5, 'E': 3, 'C': 2.5},
         'subjects': {'psychology': 0.5, 'biology': 0.5}}]
    st = {'group': 'tajrobi', 'riasec': p, 'liked': {'biology': 5, 'chemistry': 4, 'math': 2},
          'grades': {'biology': 85, 'chemistry': 60, 'math': 30, 'physics': 25}}
    r1, r2 = kk_match.match(st, profs), kk_match.match(st, list(reversed(profs)))
    check('deterministic regardless of order', r1 == r2)
    check('group filter drops riazi-only', [x['id'] for x in r1['rows']] == ['medicine', 'psych'])
    check('reason interest shared', any(x.startswith('interest:') for x in r1['rows'][0]['reasons']))
    st2 = dict(st, liked={'math': 1}, grades={'math': 95, 'biology': 40, 'chemistry': 45})
    r3 = kk_match.match(dict(st2, group='riazi'), profs)
    check('strong-grade-low-liking flagged', any('strong-grade-low-liking' in x for x in r3['rows'][0]['reasons']))
    check('subject fit needs 30% coverage', kk_match.subject_fit({'english': 1.0}, {'math': 0.9, 'english': 0.1}) is None)
    # extraction helpers
    check('clean line presentation forms', kk_extract.clean_line('ﺷﯿﻤﯽ') == 'شیمی')
    check('number regex', kk_extract.NUM.findall('ریاضی 3 واحد 48 ساعت -2') == ['3', '48', '-2'])
    check('msrt row 5-run', kk_extract.parse_msrt('ندارد 32 16 1 1 2 تحلیل گرافیکی و اکتشافی دادهها 1') == ('تحلیل گرافیکی و اکتشافی دادهها', 2.0, 1.0))
    check('msrt row prereq digits', kk_extract.parse_msrt('ریاضی عمومی 1 64 4 4 ریاضی عمومی 2 4') == ('ریاضی عمومی 2', 4.0, 0.0))
    check('msrt total line ignored', kk_extract.parse_msrt('23 جمع') is None)
    n = 35
    print('KONKUR test %s: %d checks, %d failed' % ('OK' if not FAILS else '[FAIL]', n, len(FAILS)))
    for f in FAILS:
        print('  FAIL ' + f)
    return 1 if FAILS else 0


if __name__ == '__main__':
    raise SystemExit(main())
