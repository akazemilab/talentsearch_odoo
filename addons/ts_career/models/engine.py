"""CAREER-MATCH: one person -> every O*NET occupation (free personal career match). Pure and deterministic.

Port of MATCH-v0.2.2 (docs ONET_M3 spec + amendments: domain fits, PCT-v0 within-person percentiles, EV-v1 evidence
gate) with one addition for the free product: a QUICK tier. While a person has only the interest module (evidence
0.30 < 0.50) occupations are ordered by interest fit alone and shown with their job-zone readiness, as O*NET's own
My Next Move does. Once work styles are added (evidence 0.50; abilities raise it to 0.70) the FULL tier ranks by the
combined fit.

Data: addons/ts_career/data/career_onet.json (CAREER-DATA-1, O*NET 31.0, CC BY 4.0 USDOL/ETA).
Person: {'riasec': {Realistic..Conventional: any scale}, 'styles': {work style: -1..1} | None,
         'abilities': {O*NET ability: percentile 0-100} | None, 'values': {...} | None, 'jz': 1..5 | None}
Every weight and threshold is a labelled hypothesis (not validated, not O*NET's).
"""
import bisect
import math

MODEL = 'CAREER-MATCH-v2-2026-10-13'
RIASEC = ['Realistic', 'Investigative', 'Artistic', 'Social', 'Enterprising', 'Conventional']
VALUES = ['Achievement', 'Independence', 'Recognition', 'Relationships', 'Support', 'Working Conditions']
W = {'I': 0.30, 'WS': 0.20, 'AB': 0.20, 'SK': 0.10, 'KN': 0.10, 'V': 0.10}     # W-v0
EVIDENCE_MIN = 0.5      # EV-free-v1 (owner 2026-10-13, fewest steps): interests + work styles rank; EV-v1 was 0.6
FULL_MIN_RANKED = 20            # fewer ranked occupations than this -> QUICK tier
TAU_AB = 10.0                   # TAU-v0, percentile points
AB_MIN_IM = 1.5
CLINIC_MIN_IM = 2.5
CLINIC_DEX = ['Arm-Hand Steadiness', 'Manual Dexterity', 'Finger Dexterity', 'Speed of Limb Movement']
JZ_RULE = 'JZ-v0: education level 1-5, +1 with 5 or more years of related work (max 5)'
SHORT_N = 10            # SHORT-v1: the main list is at most 10 occupations ...
SHORT_MIN = 5           # ... and at least 5 (filled from the ranking when the gates leave fewer)
AREA_MAX = 4            # at most 4 from one occupational area (SOC major group), so other strong areas show too
GATE_I = 0.85           # interest fit among the person's top 15 %
GATE_WS = 0.50          # work styles: the job's important styles lean toward the person's stronger side
GATE_AB = 0.70          # abilities: no large shortfall on the job's important measured abilities
AREA_FA = {'11': 'مدیریت', '13': 'کسب‌وکار و امور مالی', '15': 'رایانه و ریاضیات', '17': 'معماری و مهندسی',
           '19': 'علوم زیستی، فیزیکی و اجتماعی', '21': 'خدمات اجتماعی و مشاوره', '23': 'حقوق', '25': 'آموزش و کتابخانه',
           '27': 'هنر، طراحی، رسانه و ورزش', '29': 'پزشکی و سلامت', '31': 'پشتیبانی سلامت', '33': 'خدمات حفاظتی و ایمنی',
           '35': 'غذا و پذیرایی', '37': 'نگهداری ساختمان و فضای سبز', '39': 'خدمات شخصی', '41': 'فروش',
           '43': 'امور اداری و دفتری', '45': 'کشاورزی، ماهیگیری و جنگل', '47': 'ساخت‌وساز', '49': 'نصب، تعمیر و نگهداری',
           '51': 'تولید', '53': 'حمل‌ونقل', '55': 'نظامی'}


def hex_dist(a, b):
    d = abs(a - b)
    return min(d, 6 - d)


def c_index(person_code, job_ih):
    """C-INDEX-v0 (Brown & Gore 1994): congruence of the person's top-3 interest letters with the job's high-point
    codes on Holland's hexagon; 3*first + 2*second + 1*third, each 3 - hexagon distance; 0..1 over the letters present."""
    got = mx = 0.0
    for w, p, j in zip((3, 2, 1), person_code, job_ih):
        if not j:
            continue
        got += w * (3 - hex_dist(p, j - 1))
        mx += w * 3
    return got / mx if mx else None


def pearson(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx < 1e-9 or sy < 1e-9:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


class Ref:
    """Occupation-side reference: ability groups and the sorted required levels (RE-v0 percentiles)."""

    def __init__(self, data):
        self.lv = data['lv_sorted']
        ids = data['ab_id']
        cog = [a for a, i in ids.items() if i.startswith('1.A.1.')]
        psy = [a for a, i in ids.items() if i.startswith('1.A.2.')]
        phys = [a for a, i in ids.items() if i.startswith('1.A.3.')]
        sens = [a for a, i in ids.items() if i.startswith('1.A.4.')]
        self.testable = sorted(set(cog + psy) - set(CLINIC_DEX))
        self.clinic = sorted(set(phys + sens + CLINIC_DEX))

    def q(self, ability, lv):
        arr = self.lv.get(ability) or []
        return 100.0 * bisect.bisect_left(arr, lv) / len(arr) if arr else 50.0


def jz_from(edu, exp):
    """JZ-v0. edu 1-5 (below diploma .. graduate), exp in {'0','1_2','3_5','5plus'}."""
    if not edu:
        return None
    return min(5, int(edu) + (1 if exp == '5plus' else 0))


def readiness(jz_p, jz_o):
    if not jz_o or not jz_p:
        return 'UNKNOWN'
    jz_o = int(jz_o)
    if jz_p >= jz_o:
        return 'READY'
    return 'NEAR' if jz_o - jz_p == 1 else 'FAR'


def fit_interests(riasec, occ):
    oi = occ.get('oi')
    if not riasec or not oi:
        return None, 0.0, {}
    r = pearson([float(riasec[k]) for k in RIASEC], oi)
    if r is None:
        return None, 0.0, {}
    top = sorted(range(6), key=lambda i: (-oi[i], i))[:2]
    pcode = [RIASEC.index(k) for k in person_top(riasec, 3)]
    c = c_index(pcode, occ.get('ih') or [])
    f = (1 + r) / 2 if c is None else 0.5 * (1 + r) / 2 + 0.5 * c       # INT-v2: profile shape + top-code congruence
    return f, 1.0, {'r': round(r, 4), 'c': None if c is None else round(c, 4), 'job_top': [RIASEC[i] for i in top]}


def fit_values(values, occ):
    wv = occ.get('wv')
    if not values or not wv:
        return None, 0.0, {}
    r = pearson([float(values[k]) for k in VALUES], wv)
    if r is None:
        return None, 0.0, {}
    return (1 + r) / 2, 1.0, {'r': round(r, 4)}


def fit_styles(styles, occ):
    st = occ.get('ws')
    if not styles or not st:
        return None, 0.0, {}
    num = den = 0.0
    contrib = []
    for name in sorted(st):
        wi = st[name][0]
        if wi is None or name not in styles:
            continue
        num += wi * styles[name]
        den += abs(wi)
        contrib.append((round(wi * styles[name], 6), name, wi, styles[name]))
    if den < 1e-9:
        return None, 0.0, {}
    contrib.sort()
    plus = [n for c, n, wi, s in reversed(contrib) if c > 0.15 and wi >= 1.5][:2]
    minus = [n for c, n, wi, s in contrib if c < -0.15 and wi >= 1.0][:2]
    return (1 + num / den) / 2, 1.0, {'plus': plus, 'minus': minus}


def fit_abilities(P, occ, ref):
    ab = occ.get('ab')
    if not P or not ab:
        return None, 0.0, {}
    w_meas = w_test = pen = 0.0
    short, support = [], []
    for a in ref.testable:
        v = ab.get(a)
        if not v or v[0] is None or v[1] is None or v[2] or v[3] or v[0] < AB_MIN_IM:
            continue
        w = (v[0] - 1) / 4
        w_test += w
        if a not in P:
            continue
        q = ref.q(a, v[1])
        g = max(0.0, q - P[a] - TAU_AB)
        p = min(1.0, g / 50)
        w_meas += w
        pen += w * p
        if g > 0:
            short.append((-(w * p), a))
        elif v[0] >= 3:
            support.append((-v[0], a))
    if w_test < 1e-9 or w_meas < 1e-9:
        return None, 0.0, {}
    return 1 - pen / w_meas, w_meas / w_test, {'plus': [a for _, a in sorted(support)[:2]],
                                               'minus': [a for _, a in sorted(short)[:2]]}


def clinic_demands(occ, ref):
    ab = occ.get('ab') or {}
    out = []
    for a in ref.clinic:
        v = ab.get(a)
        if v and v[0] is not None and not v[2] and not v[3] and v[0] >= CLINIC_MIN_IM:
            out.append((-v[0], a))
    return [a for _, a in sorted(out)][:6]


def _percentiles(rows):
    """PCT-v0: mid-rank percentile (0-1) of each domain fit among this person's scoreable occupations."""
    for d in W:
        vals = sorted(r['fit'][d] for r in rows if r['fit'].get(d) is not None and r['cov'][d] > 0)
        n = len(vals)
        for r in rows:
            f = r['fit'].get(d)
            if f is None or r['cov'][d] <= 0 or not n:
                r['pct'][d] = None
            else:
                lo, hi = bisect.bisect_left(vals, f), bisect.bisect_right(vals, f)
                r['pct'][d] = (lo + 0.5 * (hi - lo)) / n


def _combine(pct, cov, measured=()):
    """NEUTRAL-v1: a domain the person completed but the job has no data for counts as the middle (0.5), so a job
    cannot rise to the top by missing the evidence that would have checked it."""
    num = den = 0.0
    for d, w in W.items():
        f, c = pct.get(d), cov.get(d, 0.0)
        if (f is None or c <= 0) and d in measured and d != 'I':
            f, c = 0.5, 1.0
        if f is None or c <= 0:
            continue
        num += w * c * f
        den += w * c
    return (num / den if den > 0 else None), den / sum(W.values())


def level(score, tier):
    """Plain level of fit for the reader (not a verdict). QUICK: interest correlation; FULL: combined percentile."""
    if score is None:
        return 'none'
    hi, mid = (0.80, 0.60) if tier == 'quick' else (0.85, 0.65)
    return 'high' if score >= hi else ('medium' if score >= mid else 'low')


def match(person, data, ref):
    rows = []
    for code in sorted(data['occ']):
        occ = data['occ'][code]
        fit, cov, info = {}, {}, {}
        fit['I'], cov['I'], info['I'] = fit_interests(person.get('riasec'), occ)
        fit['V'], cov['V'], info['V'] = fit_values(person.get('values'), occ)
        fit['WS'], cov['WS'], info['WS'] = fit_styles(person.get('styles'), occ)
        fit['AB'], cov['AB'], info['AB'] = fit_abilities(person.get('abilities'), occ, ref)
        fit['SK'], cov['SK'], info['SK'] = None, 0.0, {}
        fit['KN'], cov['KN'], info['KN'] = None, 0.0, {}
        rows.append({'code': code, 'fit': fit, 'cov': cov, 'pct': {}, 'info': info, 'jz': int(occ['jz']) if occ.get('jz') else None,
                     'ready': readiness(person.get('jz'), occ.get('jz'))})
    _percentiles(rows)
    measured = {d for d in ('I', 'WS', 'AB', 'V') if any(x['cov'][d] > 0 for x in rows)}
    for r in rows:
        f, e = _combine(r['pct'], r['cov'], measured)
        r['FIT'], r['evidence'] = f, e
        r['status'] = 'NOT_SCOREABLE' if f is None else ('LOW_EVIDENCE' if e < EVIDENCE_MIN - 1e-9 else 'RANKED')
    ranked = [r for r in rows if r['status'] == 'RANKED']
    tier = 'full' if len(ranked) >= FULL_MIN_RANKED else 'quick'
    if tier == 'full':
        order = sorted(ranked, key=lambda r: (-r['FIT'], -(r['fit']['I'] or 0), r['code']))
        for r in order:
            r['score'] = r['FIT']
    else:
        order = sorted((r for r in rows if r['fit']['I'] is not None), key=lambda r: (-r['fit']['I'], r['code']))
        for r in order:
            r['score'] = r['fit']['I']
    short, per_area = [], {}
    for r in order:
        p = r['pct']
        if per_area.get(r['code'][:2], 0) >= AREA_MAX:
            continue
        if (p.get('I') or 0) < GATE_I:
            continue
        if (r['fit']['WS'] is not None and r['fit']['WS'] < GATE_WS) or (r['fit']['AB'] is not None and r['fit']['AB'] < GATE_AB):
            continue
        short.append(r['code'])
        per_area[r['code'][:2]] = per_area.get(r['code'][:2], 0) + 1
        if len(short) >= SHORT_N:
            break
    for r in order:
        if len(short) >= SHORT_MIN:
            break
        if r['code'] not in short:
            short.append(r['code'])
    short = set(short)
    out = []
    for i, r in enumerate(order):
        out.append({'rank': i + 1, 'code': r['code'], 'score': round(r['score'], 4), 'level': level(r['score'], tier),
                    'short': r['code'] in short, 'area': r['code'][:2],
                    'ready': r['ready'], 'jz': r['jz'], 'evidence': round(r['evidence'], 3),
                    'fit': {d: (round(v, 4) if v is not None else None) for d, v in r['fit'].items() if d in ('I', 'WS', 'AB', 'V')},
                    'I': r['info']['I'], 'WS': r['info']['WS'], 'AB': r['info']['AB'],
                    'clinic': clinic_demands(data['occ'][r['code']], ref)})
    domains = [d for d in ('I', 'WS', 'AB', 'V') if any(x['cov'][d] > 0 for x in rows)]
    return {'model': MODEL, 'data': data.get('version'), 'tier': tier, 'domains': domains, 'n': len(out), 'rows': out,
            'n_short': sum(1 for x in out if x['short'])}


def person_top(riasec, n=3):
    return sorted(RIASEC, key=lambda k: (-float(riasec[k]), RIASEC.index(k)))[:n]


def explain_fa(row, person, fa):
    """Persian reasons for one occupation. fa = {'riasec': {..}, 'ws': WS_FA, 'ab': AB_FA}. Returns (why, watch)."""
    why, watch = [], []
    I = row.get('I') or {}
    if I.get('r') is not None and person.get('riasec'):
        p = '» و «'.join(fa['riasec'][k] for k in person_top(person['riasec'], 2))
        j = '» و «'.join(fa['riasec'][k] for k in I['job_top'])
        line = 'علایق شما بیشتر «%s» است و این شغل بیشتر «%s».' % (p, j)
        (why if I['r'] >= 0.5 else watch).append(line)
    for n in (row.get('WS') or {}).get('plus', []):
        why.append('«%s» در این شغل کمک می‌کند و در شما پررنگ‌تر از ویژگی‌های دیگرتان است.' % fa['ws'].get(n, n))
    for n in (row.get('WS') or {}).get('minus', []):
        watch.append('این شغل به «%s» تکیه دارد و این ویژگی در شما کم‌رنگ‌تر است.' % fa['ws'].get(n, n))
    for n in (row.get('AB') or {}).get('plus', []):
        why.append('توانایی «%s» شما به نیاز این شغل می‌رسد.' % fa['ab'].get(n, n))
    for n in (row.get('AB') or {}).get('minus', []):
        watch.append('این شغل به «%s» بیشتری از آنچه امروز نشان دادید نیاز دارد.' % fa['ab'].get(n, n))
    rd = row.get('ready')
    if rd == 'READY':
        why.append('تحصیلات و سابقهٔ شما به سطح آمادگی این شغل می‌رسد.')
    elif rd == 'NEAR':
        watch.append('برای این شغل معمولاً یک پله آموزش یا سابقهٔ بیشتر لازم است.')
    elif rd == 'FAR':
        watch.append('برای این شغل معمولاً دو پله یا بیشتر آموزش یا سابقه لازم است.')
    return why, watch
