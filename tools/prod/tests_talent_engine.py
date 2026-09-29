#!/usr/bin/env python3
"""Golden tests of the pure matrix engine against the book's class example table
(docx Table 5). Runs anywhere: python3 tests_talent_engine.py [path/to/engine_matrix.py]"""
import importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', '..', 'addons', 'ts_talent', 'models', 'engine_matrix.py')
spec = importlib.util.spec_from_file_location('engine_matrix', path)
E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
tpath = os.path.join(os.path.dirname(path), 'text.py')
spec = importlib.util.spec_from_file_location('tt_text', tpath)
T = importlib.util.module_from_spec(spec); spec.loader.exec_module(T)

results = []
def check(name, ok, detail=''):
    results.append(bool(ok)); print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))
def close(a, b, tol=0.02):
    return abs(a - b) <= tol

FIELDS = ['معارف اسلامی', 'فارسی', 'مطالعات اجتماعی', 'علوم تجربی', 'فرهنگ و هنر', 'تربیت بدنی', 'ریاضی']
SC = {  # the book's five basic rows
    'ANA': [46.67, 73.33, 60, 40, 66.67, 53.33, 66.67],
    'EXP': [60, 80, 86.67, 86.67, 33.33, 20, 26.67],
    'ACA': [93.33, 80, 86.67, 73.33, 73.33, 60, 86.67],
    'NOV': [60, 73.33, 66.67, 66.67, 26.67, 40, 46.67],
    'DUT': [66.67, 40, 46.67, 80, 60, 46.67, 53.33],
}
COMP = {  # the book's composite rows (values printed in the table)
    'TOT': [65.33, 69.33, 69.34, 69.33, 52, 44, 56],
    'INT': [66.67, 77.78, 77.78, 66.67, 57.78, 44.44, 60],
    'ACT': [63.34, 56.67, 56.67, 73.34, 43.34, 43.34, 50],
    'CRE': [55.56, 75.55, 71.11, 64.45, 42.22, 37.78, 46.67],
    'SCH': [80, 60, 66.67, 76.67, 66.67, 53.34, 70],
    'CRT': [53.34, 73.33, 63.34, 53.34, 46.67, 46.67, 56.67],
    'CRP': [60, 76.67, 76.67, 76.67, 30, 30, 36.67],
}
def answers_for(fi):
    a = [0] * 15
    for k, code in enumerate(E.SCALES):
        total = round(SC[code][fi] * 0.15)
        base, rem = divmod(total, 3)
        for j in range(3):
            a[k + 5 * j] = base + (1 if j < rem else 0)
    return a
fields = [{'label': FIELDS[i], 'answers': answers_for(i), 'seconds': 240} for i in range(7)]
res = E.score_matrix(fields)
check('fixture answers are valid 1-5 integers', all(1 <= v <= 5 for f in fields for v in f['answers']))
ok = all(close(res['fields'][i]['scales'][c], SC[c][i]) for c in SC for i in range(7))
check('5 scales reproduce the book table (+-0.02)', ok)
bad = [(c, FIELDS[i], round(res['fields'][i]['composites'][c], 2), COMP[c][i]) for c in COMP for i in range(7) if not close(res['fields'][i]['composites'][c], COMP[c][i], 0.021)]
check('7 composites reproduce the book table (+-0.02)', not bad, str(bad[:4]))
check('mean TOT = 60.76 (book)', close(res['mean']['TOT'], 60.76, 0.01), '%.3f' % res['mean']['TOT'])
check('row means match (ANA 58.1, EXP 56.19, ACA 79.05, NOV 54.29, DUT 56.19)',
      all(close(res['mean'][c], v, 0.01) for c, v in (('ANA', 58.1), ('EXP', 56.19), ('ACA', 79.05), ('NOV', 54.29), ('DUT', 56.19))))
check('scale range: all-ones = 20, all-fives = 100',
      close(E.score_field([1] * 15)[0]['ANA'], 20, 1e-9) and close(E.score_field([5] * 15)[0]['DUT'], 100, 1e-9))
check('item i belongs to scale (i-1) mod 5', [E.scale_of_item(i) for i in range(6)] == ['ANA', 'EXP', 'ACA', 'NOV', 'DUT', 'ANA'])

P = E.interpret(res)
check('L1 overall 60.76', close(P['overall']['score'], 60.76, 0.01))
b = P['brief']
check('L2 brief: best ability = هوش تحصیلی 79.05', b['abilities'] == ['ACA'] and close(b['ability_score'], 79.05, 0.01))
check('L2 brief: best fields = exact tie incl. مطالعات اجتماعی (book picked it)', 'مطالعات اجتماعی' in b['fields'] and len(b['fields']) == 3, str(b['fields']))
check('L2 brief score about 74.2', close(b['score'], 74.2, 0.05), '%.2f' % b['score'])
c = P['composite']
check('L3 هوش: فارسی (book) tied exactly with مطالعات اجتماعی (table shows فارسی- اجتماعی) 77.78', c['intel']['fields'] == ['فارسی', 'مطالعات اجتماعی'] and close(c['intel']['score'], 77.78, 0.01))
check('L3 کنش علوم تجربی 73.34', c['action']['fields'] == ['علوم تجربی'] and close(c['action']['score'], 73.34, 0.02))
f = P['focal']
check('L4 focal intel: تحصیلی in معارف اسلامی 93.33', (f['intel']['ability'], f['intel']['field']) == ('ACA', 'معارف اسلامی') and close(f['intel']['score'], 93.33, 0.01))
check('L4 focal action: وظیفه‌مندی in علوم تجربی 80', (f['action']['ability'], f['action']['field']) == ('DUT', 'علوم تجربی') and close(f['action']['score'], 80, 0.01))
d = P['detail']
check('L5 dominant label = وظیفه‌مندی تحصیلی', d['intel_mode'] == ['ACA'] and d['action_mode'] == ['DUT'] and not d['combined'], str(d['counts']))
check('L5 fields include the book\'s فارسی، علوم تجربی، معارف اسلامی', {'فارسی', 'علوم تجربی', 'معارف اسلامی'} <= set(d['fields']), str(d['fields']))
check('L5 per-field labels follow the book row (4 تحصیلی, 3 تجربی)', sum(1 for p in P['per_field'] if p['intel'] == 'ACA') == 4 and sum(1 for p in P['per_field'] if p['intel'] == 'EXP') == 3)
t = P['types']
check('L6 خلّاقیّت فارسی 75.55', t['CRE']['fields'] == ['فارسی'] and close(t['CRE']['score'], 75.55, 0.01))
check('L6 استعداد تحصیلی معارف اسلامی 80', t['SCH']['fields'] == ['معارف اسلامی'])
check('L6 خلّاقیّت نظری فارسی 73.33', t['CRT']['fields'] == ['فارسی'])
check('L6 خلّاقیّت عملی = فارسی، مطالعات اجتماعی، علوم تجربی (book)', set(t['CRP']['fields']) == {'فارسی', 'مطالعات اجتماعی', 'علوم تجربی'})
w = P['weak']
check('L7 weakest ability نوسودمندی 54.29 / field تربیت بدنی 44', w['abilities'] == ['NOV'] and w['fields'] == ['تربیت بدنی'] and close(w['ability_score'], 54.29, 0.01) and close(w['field_score'], 44, 0.01))
check('near set uses gap 10 (ANA 58.1 is near NOV 54.29)', 'ANA' in w['abilities_near'])
pr = P['programs']
check('programs use the book names', pr['SCH'] == ['تسریعی معارف اسلامی'] and pr['CRE'] == ['غنی‌سازی فارسی'] and pr['CRT'] == ['غنی‌سازی تحلیلی فارسی'], str(pr['CRE']))
check('compensatory program names weakest field and best ability', pr['compensatory'] == 'آموزش جبرانی تربیت بدنی با بهره‌گیری از هوش تحصیلی', pr['compensatory'])
check('per-field policy for مطالعات اجتماعی is نوسودمندی تجربی (tie -> first) ', [p for p in P['per_field'] if p['label'] == 'مطالعات اجتماعی'][0]['policy'] in ('نوسودمندی تجربی',), '')

# single field: only overall + per-field abilities
one = E.interpret(E.score_matrix(fields[:1]))
check('1 field: no cross-field levels', 'brief' not in one and 'weak' not in one and len(one['per_field']) == 1)
two = E.interpret(E.score_matrix(fields[:2]))
check('2 fields: all levels present', all(k in two for k in ('brief', 'composite', 'focal', 'detail', 'types', 'weak', 'programs')))
eight = E.interpret(E.score_matrix([dict(fields[i % 7], label='%s %d' % (FIELDS[i % 7], i)) for i in range(8)]))
check('8 fields ok', eight['n_fields'] == 8)

# errors
def raises(fn):
    try: fn()
    except E.ScoringError: return True
    except Exception: return False
    return False
check('14 answers -> error', raises(lambda: E.score_field([3] * 14)))
check('answer 6 -> error', raises(lambda: E.score_field([3] * 14 + [6])))
check('answer 0 -> error', raises(lambda: E.score_field([0] + [3] * 14)))
check('bool answer -> error', raises(lambda: E.score_field([True] + [3] * 14)))
check('duplicate labels -> error', raises(lambda: E.score_matrix([dict(fields[0]), dict(fields[0])])))
check('no fields -> error', raises(lambda: E.score_matrix([])))

# flags and reproducibility
fl = E.score_matrix([{'label': 'a', 'answers': [3] * 15, 'seconds': 10}, {'label': 'b', 'answers': [1, 2, 3, 4, 5] * 3, 'seconds': None}])
check('straight + fast flags; None seconds is not fast', fl['fields'][0]['flags'] == {'straight': True, 'fast': True} and fl['fields'][1]['flags'] == {'straight': False, 'fast': False})
check('deterministic hashes', E.score_matrix(fields)['output_hash'] == res['output_hash'] and E.score_matrix(fields[::-1])['input_hash'] != res['input_hash'])

# text helpers
check('clean_label unifies ي/ك and spaces', T.clean_label('  رياضي   كاربردي ') == 'ریاضی کاربردی')
check('label cap 80', len(T.clean_label('الف' * 200)) == 80)
check('norm_label ignores spaces/ZWNJ/digit style', T.norm_label('می خواهم ۱') == T.norm_label('می‌خواهم 1'))
ITEMS = os.path.join(HERE, '..', '..', 'addons', 'ts_talent', 'data', 'talent_items.json')
if os.path.exists(ITEMS):
    import json
    items = json.load(open(ITEMS, encoding='utf-8'))
    check('15 items', len(items) == 15)
    ok = True
    for txt in items:
        segs = T.item_segments(txt, 'ریاضی')
        shown = ''.join(s for s, _ in segs)
        ok &= not T.PLACEHOLDER.search(shown) and any(fl_ for _, fl_ in segs)
    check('every item shows the field name and none keeps «این زمینه/قلمرو/عرصه»', ok)
    import hashlib
    check('stored items are verbatim (canonical md5 of the 15 form headers)', hashlib.md5(json.dumps(items, ensure_ascii=False).encode()).hexdigest() == '9e15862e962e10492586d36c1ca2c642')

print('SUMMARY %d/%d passed' % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
