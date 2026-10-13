#!/usr/bin/env python3
"""Golden tests for ts_career/models/engine.py (pure; runs anywhere with the repo: python3 tests_career_engine.py)."""
import importlib.util
import json
import os
import sys

ADDONS = os.environ.get('TS_ADDONS') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'addons')


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ADDONS, rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


E = load('career_engine', 'ts_career/models/engine.py')
data = json.load(open(os.path.join(ADDONS, 'ts_career/data/career_onet.json'), encoding='utf-8'))
ref = E.Ref(data)
RES = []


def check(name, ok):
    RES.append(bool(ok))
    print(('PASS ' if ok else 'FAIL ') + name)


check('data has 923 occupations with interests', len(data['occ']) == 923 and all(o['oi'] for o in data['occ'].values()))
check('ability reference built', len(ref.testable) >= 20 and len(ref.clinic) >= 20)
check('jz rule', E.jz_from(4, '0') == 4 and E.jz_from(4, '5plus') == 5 and E.jz_from(5, '5plus') == 5 and E.jz_from(None, '0') is None)
check('readiness', E.readiness(4, '4') == 'READY' and E.readiness(3, '4') == 'NEAR' and E.readiness(2, '5') == 'FAR' and E.readiness(None, '3') == 'UNKNOWN')

inv = {'Realistic': 1.5, 'Investigative': 4.8, 'Artistic': 2.0, 'Social': 3.9, 'Enterprising': 1.7, 'Conventional': 2.2}
p_quick = {'riasec': inv, 'jz': 5}
a = E.match(p_quick, data, ref)
b = E.match(dict(p_quick), data, ref)
check('quick tier with interests only', a['tier'] == 'quick' and a['domains'] == ['I'])
check('deterministic', a == b)
check('every occupation ordered', a['n'] == 923 and [r['rank'] for r in a['rows'][:3]] == [1, 2, 3])
top = a['rows'][0]
occ = data['occ'][top['code']]
check('top job is investigative/social-leaning', set(top['I']['job_top']) & {'Investigative', 'Social'})
check('scores sorted', all(a['rows'][i]['score'] >= a['rows'][i + 1]['score'] for i in range(50)))
check('level words', top['level'] in ('high', 'medium', 'low'))
flat = dict(p_quick, riasec={k: 3 for k in E.RIASEC})
check('flat interests -> nothing ranked', E.match(flat, data, ref)['n'] == 0)

styles = {'Achievement Orientation': 0.5, 'Attention to Detail': 0.6, 'Intellectual Curiosity': 0.8, 'Empathy': 0.4,
          'Social Orientation': -0.2, 'Leadership Orientation': -0.5, 'Stress Tolerance': 0.1, 'Dependability': 0.5}
abil = {n: 70.0 for n in ref.testable[:10]}
p_full = dict(p_quick, styles=styles, abilities=abil)
f = E.match(p_full, data, ref)
check('full tier with styles + abilities', f['tier'] == 'full' and set(f['domains']) >= {'I', 'WS', 'AB'})
check('full rows carry evidence >= 0.5', all(r['evidence'] >= 0.5 for r in f['rows']))
p_ws = dict(p_quick, styles=styles)
check('personality alone reaches full tier', E.match(p_ws, data, ref)['tier'] == 'full')
check('full ranking differs from quick', [r['code'] for r in f['rows'][:10]] != [r['code'] for r in a['rows'][:10]])
fa = {'riasec': {k: k for k in E.RIASEC}, 'ws': {}, 'ab': {}}
why, watch = E.explain_fa(f['rows'][0], p_full, fa)
check('explanations', len(why) >= 1 and all(isinstance(x, str) for x in why + watch))
check('c-index: same top code = 1, opposite = low', E.c_index([1, 0, 4], [2, 1, 5]) == 1.0 and E.c_index([1, 0, 4], [4, 3, 1]) < 0.4)
check('short list of 5-10', 5 <= f['n_short'] <= 10 and 5 <= a['n_short'] <= 10)
from collections import Counter
check('at most 4 per area', max(Counter(r['area'] for r in f['rows'] if r['short']).values()) <= E.AREA_MAX)
check('every area has a Persian name', all(r['area'] in E.AREA_FA for r in f['rows']))
check('clinic list is short', all(len(r['clinic']) <= 6 for r in f['rows']))

print('SUMMARY %d/%d passed' % (sum(RES), len(RES)))
sys.exit(0 if all(RES) else 1)
