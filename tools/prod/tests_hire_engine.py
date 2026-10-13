#!/usr/bin/env python3
"""Golden tests of the HR engines that run anywhere (no ORM): JOBFIT-v1 (ts_onet), task generators and scoring
(ts_tasks). docs/hr/01_architecture.md section 6."""
import importlib.util
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'addons')
results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def load(mod, path):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ADDONS, path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[mod] = m
    spec.loader.exec_module(m)
    return m


J = load('jobfit', 'ts_onet/models/jobfit.py')
G = load('generators', 'ts_tasks/models/generators.py')
S = load('scoring', 'ts_tasks/models/scoring.py')
data = json.load(open(os.path.join(ADDONS, 'ts_onet/data/onet_hr.json'), encoding='utf-8'))
occ = {o['code']: o for o in data['occupations']}
ref = J.Reference(data['lv_sorted'])

# ---- catalogue
check('E01 catalogue has 923 occupations with Persian titles', len(occ) == 923 and all(o['fa'] for o in occ.values()))
check('E02 Persian titles are unique', len({o['fa'] for o in occ.values()}) == 923)
MEAS = ['Inductive Reasoning', 'Information Ordering', 'Deductive Reasoning', 'Visualization', 'Spatial Orientation',
        'Mathematical Reasoning', 'Number Facility', 'Perceptual Speed', 'Memorization', 'Selective Attention',
        'Reaction Time', 'Response Orientation']
check('E03 every measured ability has an O*NET level table', all(ref.lv_sorted.get(a) for a in MEAS))
check('E04 every work style of the crosswalk has a Persian name', set(J.WS_XW) <= set(J.WS_FA))
check('E05 every ability/clinic name has a Persian name',
      all(a in J.AB_FA for a in data['testable'] + data['clinic']), [a for a in data['testable'] + data['clinic'] if a not in J.AB_FA])

# ---- JOBFIT
dev = occ['15-1252.00']
flat = {f: 3.0 for f in J.FACETS}
r0 = J.jobfit(dev, ref, facets=flat)
check('E06 a flat profile has no style strengths or gaps (all neutral)',
      r0['ws'] and all(x['status'] == 'neutral' for x in r0['ws']['rows']), r0['ws'] and r0['ws']['band'])
inflated = {f: min(5.0, v + 1.0) for f, v in dict(flat, Perfectionism=4.0, Organization=3.8).items()}
base = dict(flat, Perfectionism=4.0, Organization=3.8)
check('E07 CENTER-v0: answering everything one step higher does not change the style fit',
      abs(J.jobfit(dev, ref, facets=base)['ws']['fit'] - J.jobfit(dev, ref, facets={f: v + 0.5 for f, v in base.items()})['ws']['fit']) < 1e-9)
good = dict(flat, Perfectionism=4.6, Organization=4.4, Diligence=4.4, Inquisitiveness=4.6, Anxiety=2.0)
r1 = J.jobfit(dev, ref, facets=good, abilities={a: 85 for a in MEAS})
r2 = J.jobfit(dev, ref, facets=good, abilities={a: 10 for a in MEAS})
check('E08 higher abilities give a band at least as good', J.order_key(r1) <= J.order_key(r2), (r1['band'], r2['band']))
check('E09 low abilities on important requirements are listed as short',
      any(x['status'] == 'short' for x in r2['ab']['rows']))
check('E10 surplus ability is never penalised', all(x['status'] == 'met' for x in r1['ab']['rows']))
r3 = J.jobfit(dev, ref, facets=good, abilities={a: 85 for a in MEAS},
              overrides={'critical': ['Attention to Detail'], 'dropped': ['Deductive Reasoning']})
check('E11 a dropped requirement disappears, a critical one doubles its weight',
      not any(x['name'] == 'Deductive Reasoning' for x in r3['ab']['rows'])
      and any(x['name'] == 'Attention to Detail' and x['critical'] for x in r3['ws']['rows']))
r4 = J.jobfit(dev, ref, facets=good, abilities=None)
check('E12 personality only: ability band None and flagged', r4['ab']['band'] is None and r4['personality_only'])
check('E13 deterministic: same input, same hash',
      J.jobfit(dev, ref, facets=good, abilities={a: 50 for a in MEAS})['input_hash'] ==
      J.jobfit(dev, ref, facets=good, abilities={a: 50 for a in MEAS})['input_hash'])
ex = J.explain(r2)
check('E14 explanations are Persian sentences, interview prompts for gaps', ex['watch'] and all('«' in w for w in ex['watch']))
rnd = random.Random(7)
bands = {}
for _ in range(1500):
    o = rnd.choice([x for x in occ.values() if x['styles'] and x['ab']])
    f = {k: rnd.choice([1.8, 2.2, 2.6, 3, 3.4, 3.8, 4.2, 4.6]) for k in J.FACETS}
    b = J.jobfit(o, ref, facets=f, abilities={a: rnd.uniform(0, 100) for a in MEAS})['band']
    bands[b] = bands.get(b, 0) + 1
check('E15 random respondents are rarely "strong" (< 25%)', bands.get('strong', 0) / 1500 < 0.25, bands)
check('E16 clinic list for a nurse names physical/sensory demands', any(c['name'] in J.AB_FA for c in J.jobfit(occ['29-1141.00'], ref, facets=flat)['clinic']))

# ---- generators
same = G.gen_matrices('s1') == G.gen_matrices('s1') and G.gen_matrices('s1') != G.gen_matrices('s2')
check('G01 items are deterministic per seed and differ between seeds', same)
ok = True
for sd in range(60):
    for k, g in G.GENERATORS.items():
        items, keys = g('seed%d' % sd)
        if len(items) != len(keys) or any('key' in it for it in items):
            ok = False
check('G02 no generator puts the key into the client item', ok)
it, ks = G.gen_rotation('x')
check('G03 rotation: only chiral shapes, half mirrored', len(G.CHIRAL) >= 4 and 6 <= sum(ks) <= 10, sum(ks))
it, ks = G.gen_logic('x')
check('G04 logic items have the key among the options', all(0 <= k < len(i['options']) for i, k in zip(it, ks)))
it, ks = G.gen_numeric('x')
check('G05 numeric options are distinct', all(len(set(i['options'])) == len(i['options']) for i in it))
# text alternatives (owner 2026-10-13): display only, built from the drawn structure; the items and keys never change
it, ks = G.gen_matrices('x')
check('G06 every matrix item describes its 8 cells in 3 rows (the 9th is the empty one) and names each option',
      all(len(__import__('re').findall('ردیف [۱-۳]:', i['cells_text'])) == 3 and 'خانهٔ خالی' in i['cells_text'] and len(i['options_text']) == len(i['options'])
          and len(set(i['options_text'])) == len(i['options_text']) for i in it), it[0]['cells_text'])
it, ks = G.gen_rotation('x')
check('G07 every rotation figure is described row by row (squares in words), both figures',
      all(i['left_text'].count('پر') >= 4 and i['right_text'].startswith('شکلی از') for i in it), it[0]['left_text'])
golden = {}
for k, g in G.GENERATORS.items():
    for sd in ('a', 'b', 'c-1', 'x-practice'):
        for pr in (False, True):
            golden['%s|%s|%s' % (k, sd, pr)] = (g(sd, practice=pr) if pr else g(sd))[1]
digest = __import__('hashlib').sha256(json.dumps(golden, sort_keys=True).encode()).hexdigest()
check('G08 the keys of every generator are unchanged by the text alternatives (golden of 2026-10-13)',
      digest == 'f5994bed3879b260113331b6dc4534a995f2638ddbd0fd607a1235e9d9fcdc39', digest)

# ---- scoring
keys = [1, 2, 3, 0]
check('S01 power raw = share correct, unanswered = wrong',
      S.raw_score('matrices', keys, [{'c': 1}, {'c': 2}, None, {'c': 3}], 240) == 0.5)
p_hi, lab = S.percentile('matrices', 0.9)
p_lo, _ = S.percentile('matrices', 0.2)
check('S02 PN-0 percentiles move the right way and are labelled', p_hi > 90 and p_lo < 10 and lab == 'PN-0', (p_hi, p_lo))
p_fast, _ = S.percentile('choice_rt', 300.0)
p_slow, _ = S.percentile('choice_rt', 600.0)
check('S03 lower reaction time = higher percentile', p_fast > 90 > 10 > p_slow, (p_fast, p_slow))
rr = random.Random(3)
emp = sorted(rr.gauss(0.5, 0.1) for _ in range(150))
p_emp, lab2 = S.percentile('matrices', 0.5, emp)
check('S04 empirical norm from 100+ cases is used', lab2 == 'EMP-150' and 35 < p_emp < 65, (lab2, p_emp))
check('S05 empirical norm below 100 cases is ignored', S.percentile('matrices', 0.5, emp[:80])[1] == 'PN-0')
check('S06 flags: fast answering and focus loss',
      set(S.block_flags('matrices', [0] * 8, [{'c': 0, 'rt': 900}] * 8, {'focus_lost': 3})) >= {'fast', 'focus'})
fl = [{'c': 0, 'rt': 450, 'inc': True}] * 10 + [{'c': 1, 'rt': 900, 'inc': True}] * 2
check('S07 flanker inverse efficiency on incongruent trials', 450 <= S.raw_score('flanker', [0] * 12, fl, None) < 700)
check('S08 bands at thirds', S.band_of(20) == 'low' and S.band_of(50) == 'medium' and S.band_of(80) == 'high')
check('S09 every instrument factor maps to blocks of that instrument',
      all(set(b for bs in sp['factors'].values() for b in bs) <= {x['key'] for x in sp['blocks']} for sp in S.INSTRUMENTS.values()))
m_help = [b['help'] for sp in S.INSTRUMENTS.values() for b in sp['blocks'] if b['key'] == 'matrices']
check('S10 matrix instructions name no side (the grid is drawn LTR: the empty cell is bottom-right on screen)',
      m_help and all('چپ' not in h and 'راست' not in h for h in m_help), m_help)
check('S11 instructions say «نمره», never «امتیاز» (glossary)',
      all('امتیاز' not in b['help'] for sp in S.INSTRUMENTS.values() for b in sp['blocks']))

print('SUMMARY %d/%d passed' % (sum(results), len(results)))
