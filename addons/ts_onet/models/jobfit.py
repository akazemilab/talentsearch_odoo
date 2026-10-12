"""JOBFIT-v1: how well ONE candidate fits ONE occupation's requirements (docs/hr/01_architecture.md section 3).

Owner decision 2026-10-12: the hiring fit uses only personality (IPIP-HEXACO facets -> O*NET work styles, WS-XW-v0)
and our own timed tasks (abilities, RE-v0). O*NET's interest, work-values and ability tools are never used for hiring
(their user materials: results "should not be used for employment or hiring decisions"). Self-rated skills are not
part of the fit.

The result is comparable across candidates for the same position (unlike MATCH-v0's within-person percentiles) and is
reported as three bands, never as a cut-off. Pure functions over plain data: golden tests run without the ORM.
"""
import bisect
import hashlib
import json

MODEL = 'JOBFIT-v1-2026-10-12'
ASSUMPTIONS = {
    'WS-XW-v0': 'Work styles are derived from IPIP-HEXACO facets by an expert crosswalk, pending psychologist review.',
    'CENTER-v0': 'Facets are centred within the person (relative strengths): uniform inflation of all answers does not '
                 'raise the fit.',
    'RE-v0': 'Ability level is compared as rank: the job\'s required level as a percentile among 910 occupations vs the '
             'candidate\'s percentile on our tasks (provisional norms until enough candidates have taken them).',
    'BAND-v1': 'Bands summarise how many weighted requirements are met; they are not validated against job performance '
               'yet and are never a cut-off.',
}

FACETS = ['Sincerity', 'Fairness', 'Greed Avoidance', 'Modesty',
          'Fearfulness', 'Anxiety', 'Dependence', 'Sentimentality',
          'Expressiveness', 'Social Boldness', 'Sociability', 'Liveliness',
          'Forgiveness', 'Gentleness', 'Flexibility', 'Patience',
          'Organization', 'Diligence', 'Perfectionism', 'Prudence',
          'Aesthetic Appreciation', 'Inquisitiveness', 'Creativity', 'Unconventionality']

FACET_FA = {
    'Sincerity': 'بی‌ریایی', 'Fairness': 'انصاف', 'Greed Avoidance': 'پرهیز از آزمندی', 'Modesty': 'فروتنی',
    'Fearfulness': 'پرهیز از خطر', 'Anxiety': 'نگرانی', 'Dependence': 'نیاز به پشتیبانی', 'Sentimentality': 'حساسیت عاطفی',
    'Expressiveness': 'بیانگری', 'Social Boldness': 'جسارت اجتماعی', 'Sociability': 'معاشرتی بودن', 'Liveliness': 'سرزندگی',
    'Forgiveness': 'گذشت', 'Gentleness': 'ملایمت', 'Flexibility': 'انعطاف در تعامل', 'Patience': 'صبوری',
    'Organization': 'نظم و سازمان‌دهی', 'Diligence': 'سخت‌کوشی', 'Perfectionism': 'کمال‌گرایی', 'Prudence': 'دوراندیشی',
    'Aesthetic Appreciation': 'زیبایی‌شناسی', 'Inquisitiveness': 'کنجکاوی', 'Creativity': 'خلاقیت',
    'Unconventionality': 'اندیشهٔ نامتعارف',
}

# WS-XW-v0 (ONET_M3_MATCHING_SPEC_V0.md section 7). Negative weight = reverse-keyed facet.
WS_XW = {
    'Achievement Orientation': {'Diligence': 1},
    'Attention to Detail': {'Perfectionism': 1, 'Organization': 1},
    'Cautiousness': {'Prudence': 1},
    'Dependability': {'Diligence': 1, 'Organization': 1},
    'Self-Confidence': {'Social Boldness': 1, 'Anxiety': -1},
    'Leadership Orientation': {'Social Boldness': 1, 'Liveliness': 0.5},
    'Social Orientation': {'Sociability': 1},
    'Cooperation': {'Flexibility': 1, 'Gentleness': 1},
    'Empathy': {'Sentimentality': 1, 'Gentleness': 0.5},
    'Humility': {'Modesty': 1, 'Greed Avoidance': 0.5},
    'Integrity': {'Fairness': 1},
    'Sincerity': {'Sincerity': 1},
    'Self-Control': {'Patience': 1, 'Prudence': 0.5},
    'Stress Tolerance': {'Anxiety': -1, 'Fearfulness': -0.5},
    'Adaptability': {'Flexibility': 1, 'Unconventionality': 0.5},
    'Innovation': {'Creativity': 1, 'Unconventionality': 0.5},
    'Intellectual Curiosity': {'Inquisitiveness': 1},
    'Tolerance for Ambiguity': {'Unconventionality': 0.5, 'Anxiety': -0.5},
    'Initiative': {'Diligence': 1, 'Social Boldness': 0.5, 'Liveliness': 0.5},
    'Optimism': {'Liveliness': 1, 'Anxiety': -0.5},
    'Perseverance': {'Diligence': 1, 'Anxiety': -0.5},
}
WS_LOW_CONFIDENCE = {'Tolerance for Ambiguity', 'Initiative', 'Optimism'}

WS_FA = {
    'Achievement Orientation': 'موفقیت‌گرایی', 'Attention to Detail': 'دقت در جزئیات', 'Cautiousness': 'احتیاط',
    'Dependability': 'قابل‌اتکا بودن', 'Self-Confidence': 'اعتمادبه‌نفس', 'Leadership Orientation': 'گرایش به رهبری',
    'Social Orientation': 'اجتماعی بودن', 'Cooperation': 'همکاری', 'Empathy': 'همدلی', 'Humility': 'فروتنی',
    'Integrity': 'درستکاری', 'Sincerity': 'صداقت', 'Self-Control': 'خویشتن‌داری', 'Stress Tolerance': 'تحمل فشار',
    'Adaptability': 'انعطاف‌پذیری', 'Innovation': 'نوآوری', 'Intellectual Curiosity': 'کنجکاوی فکری',
    'Tolerance for Ambiguity': 'تحمل ابهام', 'Initiative': 'ابتکار عمل', 'Optimism': 'خوش‌بینی', 'Perseverance': 'پشتکار',
}

AB_FA = {
    # measured by our tasks in v1
    'Inductive Reasoning': 'استدلال استقرایی', 'Information Ordering': 'ترتیب‌دهی اطلاعات',
    'Deductive Reasoning': 'استدلال قیاسی', 'Visualization': 'تجسم فضایی', 'Spatial Orientation': 'جهت‌یابی فضایی',
    'Mathematical Reasoning': 'استدلال ریاضی', 'Number Facility': 'سرعت محاسبه', 'Perceptual Speed': 'سرعت ادراک',
    'Memorization': 'حافظه', 'Selective Attention': 'توجه انتخابی', 'Reaction Time': 'زمان واکنش',
    'Response Orientation': 'سرعت انتخاب پاسخ',
    # cognitive / psychomotor, not measured in v1
    'Category Flexibility': 'انعطاف در طبقه‌بندی', 'Flexibility of Closure': 'تشخیص الگوی پنهان',
    'Fluency of Ideas': 'روانی ایده‌پردازی', 'Oral Comprehension': 'درک شفاهی', 'Oral Expression': 'بیان شفاهی',
    'Originality': 'اصالت فکری', 'Problem Sensitivity': 'حساسیت به مسئله', 'Speed of Closure': 'سرعت درک الگو',
    'Time Sharing': 'توزیع توجه', 'Written Comprehension': 'درک نوشتاری', 'Written Expression': 'بیان نوشتاری',
    'Multilimb Coordination': 'هماهنگی اندام‌ها', 'Control Precision': 'کنترل دقیق', 'Rate Control': 'کنترل زمان‌بندی',
    'Wrist-Finger Speed': 'سرعت انگشتان',
    # occupational-medicine referral only (never tested here)
    'Static Strength': 'قدرت ایستا', 'Explosive Strength': 'قدرت انفجاری', 'Dynamic Strength': 'قدرت پویا',
    'Trunk Strength': 'قدرت تنه', 'Stamina': 'استقامت بدنی', 'Extent Flexibility': 'انعطاف بدنی',
    'Dynamic Flexibility': 'انعطاف پویا', 'Gross Body Coordination': 'هماهنگی کل بدن',
    'Gross Body Equilibrium': 'تعادل بدن', 'Near Vision': 'دید نزدیک', 'Far Vision': 'دید دور',
    'Visual Color Discrimination': 'تشخیص رنگ', 'Night Vision': 'دید در شب', 'Peripheral Vision': 'دید محیطی',
    'Depth Perception': 'درک عمق', 'Glare Sensitivity': 'تحمل نور خیره‌کننده', 'Hearing Sensitivity': 'حساسیت شنوایی',
    'Auditory Attention': 'توجه شنیداری', 'Sound Localization': 'تشخیص جهت صدا', 'Speech Recognition': 'درک گفتار',
    'Speech Clarity': 'وضوح گفتار', 'Arm-Hand Steadiness': 'ثبات دست و بازو', 'Manual Dexterity': 'چالاکی دست',
    'Finger Dexterity': 'چالاکی انگشتان', 'Speed of Limb Movement': 'سرعت حرکت اندام',
}

TAU_AB = 10.0          # percentile tolerance (TAU-v0)
BIG_SHORT = 25.0       # a critical ability this far below the requirement makes the ability band 'limited'
WS_MIN_IMPACT = 1.0    # |WI| (O*NET -3..+3) from which a work style is a requirement
AB_MIN_IM = 2.5        # O*NET importance (1-5) from which an ability is a requirement
S_DEAD = 0.15          # relative style score within +-0.15 = "about the candidate's own average"
BANDS = ('strong', 'moderate', 'limited')
BAND_FA = {'strong': 'تناسب زیاد', 'moderate': 'تناسب متوسط', 'limited': 'تناسب کم', None: 'شواهد کافی نیست'}
BAND_POINTS = {'strong': 2, 'moderate': 1, 'limited': 0}


def importance_fa(wi):
    return 'بسیار مهم' if wi >= 2.5 else ('مهم' if wi >= 1.5 else 'مفید')


# ---------------------------------------------------------------- person side
def center_facets(f):
    """CENTER-v0: facet means (1-5) -> relative scores in [-1, 1] (within-person z / 2, clipped)."""
    vals = [f[k] for k in FACETS]
    m = sum(vals) / len(vals)
    sd = (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
    if sd < 1e-9:
        return {k: 0.0 for k in FACETS}
    return {k: max(-1.0, min(1.0, (f[k] - m) / (2 * sd))) for k in FACETS}


def style_scores(facets):
    c = center_facets(facets)
    return {s: sum(w * c[f] for f, w in m.items()) / sum(abs(w) for w in m.values()) for s, m in WS_XW.items()}


class Reference:
    """Occupation-side tables: each ability's required levels across rated occupations (for RE-v0 percentiles)."""

    def __init__(self, lv_sorted):
        self.lv_sorted = lv_sorted

    def q(self, ability, lv):
        arr = self.lv_sorted.get(ability) or []
        if not arr:
            return None
        return 100.0 * bisect.bisect_left(arr, lv) / len(arr)


# ---------------------------------------------------------------- requirement profile
def requirements(occ, ref, overrides=None):
    """The position's requirement profile: [{kind, name, fa, weight, critical, wi|im, q, ...}] (dropped ones removed).
    overrides = {'critical': [names], 'dropped': [names]} set by HR (max 3 critical, logged by the caller)."""
    ov = overrides or {}
    critical, dropped = set(ov.get('critical') or []), set(ov.get('dropped') or [])
    reqs = []
    for name, (wi, dr) in sorted((occ.get('styles') or {}).items()):
        if wi is None or abs(wi) < WS_MIN_IMPACT or name in dropped or name not in WS_XW:
            continue
        crit = name in critical
        reqs.append({'kind': 'WS', 'name': name, 'fa': WS_FA.get(name, name), 'wi': wi, 'sign': 1 if wi > 0 else -1,
                     'weight': abs(wi) * (2 if crit else 1), 'critical': crit, 'low_conf': name in WS_LOW_CONFIDENCE,
                     'importance_fa': importance_fa(abs(wi))})
    for name, (im, lv) in sorted((occ.get('ab') or {}).items()):
        if im is None or im < AB_MIN_IM or name in dropped:
            continue
        crit = name in critical
        reqs.append({'kind': 'AB', 'name': name, 'fa': AB_FA.get(name, name), 'im': im, 'lv': lv, 'q': ref.q(name, lv),
                     'weight': (im - 1) / 4 * (2 if crit else 1), 'critical': crit,
                     'importance_fa': importance_fa((im - 1) / 4 * 3)})
    reqs.sort(key=lambda r: (r['kind'], -r['weight'], r['name']))
    return reqs


# ---------------------------------------------------------------- fit
def _ws_part(reqs, styles):
    rows, w_all, num, w_match, w_gap, crit_gap = [], 0.0, 0.0, 0.0, 0.0, False
    for r in reqs:
        if r['kind'] != 'WS':
            continue
        s = styles.get(r['name'])
        if s is None:
            continue
        v = s * r['sign']
        status = 'match' if v >= S_DEAD else ('gap' if v <= -S_DEAD else 'neutral')
        w = r['weight']
        w_all += w
        num += w * v
        if status == 'match':
            w_match += w
        elif status == 'gap':
            w_gap += w
            crit_gap = crit_gap or r['critical']
        rows.append(dict(r, value=round(s, 4), status=status))
    if w_all < 1e-9:
        return None
    match, gap = w_match / w_all, w_gap / w_all
    if crit_gap or gap >= 0.4:
        band = 'limited'
    elif match >= 0.55 and gap <= 0.2:
        band = 'strong'
    else:
        band = 'moderate'
    return {'band': band, 'fit': round((1 + num / w_all) / 2, 6), 'match_share': round(match, 4),
            'gap_share': round(gap, 4), 'rows': rows}


def _ab_part(reqs, abilities):
    rows, unmeasured = [], []
    w_all = w_eval = w_met = pen = 0.0
    crit_big = False
    for r in reqs:
        if r['kind'] != 'AB':
            continue
        w = r['weight']
        w_all += w
        p = abilities.get(r['name']) if abilities else None
        if p is None or r['q'] is None:
            unmeasured.append(r)
            continue
        g = max(0.0, r['q'] - p - TAU_AB)
        status = 'met' if g == 0 else 'short'
        w_eval += w
        pen += w * min(1.0, g / 50)
        if status == 'met':
            w_met += w
        elif r['critical'] and r['q'] - p > BIG_SHORT:
            crit_big = True
        rows.append(dict(r, value=round(p, 1), status=status))
    if w_all < 1e-9:
        return {'band': None, 'fit': None, 'coverage': 0.0, 'rows': [], 'unmeasured': unmeasured}
    coverage = w_eval / w_all
    if w_eval < 1e-9 or coverage < 0.3:
        return {'band': None, 'fit': None, 'coverage': round(coverage, 4), 'rows': rows, 'unmeasured': unmeasured}
    met = w_met / w_eval
    if crit_big or met < 0.5:
        band = 'limited'
    elif met >= 0.8 and not any(x['critical'] and x['status'] == 'short' for x in rows):
        band = 'strong'
    else:
        band = 'moderate'
    return {'band': band, 'fit': round(1 - pen / w_eval, 6), 'met_share': round(met, 4), 'coverage': round(coverage, 4),
            'rows': rows, 'unmeasured': unmeasured}


def overall_band(ws_band, ab_band):
    have = [BAND_POINTS[b] for b in (ws_band, ab_band) if b]
    if not have:
        return None
    m = sum(have) / len(have)
    return 'strong' if m >= 1.5 else ('moderate' if m >= 0.5 else 'limited')


def jobfit(occ, ref, facets=None, abilities=None, overrides=None):
    """facets: {facet: mean 1-5} (IPIP-HEXACO) or None; abilities: {O*NET ability: percentile 0-100} or None.
    Returns a plain dict (stored as JSON on the candidate's record) with a deterministic hash."""
    reqs = requirements(occ, ref, overrides)
    styles = style_scores(facets) if facets else None
    ws = _ws_part(reqs, styles) if styles else None
    ab = _ab_part(reqs, abilities or {})
    band = overall_band(ws and ws['band'], ab['band'])
    fits = [x for x in ((ws or {}).get('fit'), ab.get('fit')) if x is not None]
    out = {
        'model': MODEL, 'code': occ.get('code'), 'band': band, 'band_fa': BAND_FA[band],
        'fit': round(sum(fits) / len(fits), 6) if fits else None,
        'ws': ws, 'ab': ab, 'personality_only': ab['band'] is None,
        'clinic': [{'name': n, 'fa': AB_FA.get(n, n), 'im': im} for n, im in (occ.get('clinic') or [])],
        'overrides': {'critical': sorted((overrides or {}).get('critical') or []),
                      'dropped': sorted((overrides or {}).get('dropped') or [])},
    }
    payload = json.dumps([occ.get('code'), facets, abilities, out['overrides']], sort_keys=True, ensure_ascii=False)
    out['input_hash'] = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return out


def order_key(res):
    """Sort candidates: band first (strong, moderate, limited, none), then the continuous fit (never shown as a number)."""
    rank = {'strong': 0, 'moderate': 1, 'limited': 2, None: 3}[res.get('band')]
    return (rank, -(res.get('fit') or 0.0))


# ---------------------------------------------------------------- explanation (Persian, EXPL-HR-v1)
def explain(res, top=3):
    """{'why': [...], 'watch': [...], 'unmeasured': [...]} in short Persian sentences for HR."""
    why, watch = [], []
    ws, ab = res.get('ws') or {}, res.get('ab') or {}
    for r in sorted([x for x in ws.get('rows', []) if x['status'] == 'match'], key=lambda x: -x['weight'])[:top]:
        if r['sign'] > 0:
            why.append('«%s» از نقاط قوت نسبی داوطلب است و برای این شغل %s است.' % (r['fa'], r['importance_fa']))
        else:
            why.append('«%s» در داوطلب کمتر از دیگر ویژگی‌هایش است؛ این شغل به آن نیاز ندارد.' % r['fa'])
    for r in sorted([x for x in ab.get('rows', []) if x['status'] == 'met'], key=lambda x: -x['weight'])[:top]:
        why.append('توانایی «%s» در حد نیاز این شغل یا بالاتر است.' % r['fa'])
    for r in sorted([x for x in ws.get('rows', []) if x['status'] == 'gap'], key=lambda x: -x['weight'])[:top]:
        if r['sign'] > 0:
            watch.append('«%s» برای این شغل %s است و در نیمرخ داوطلب کمتر از دیگر ویژگی‌هایش است%s.' % (
                r['fa'], r['importance_fa'], '؛ در مصاحبه بپرسید' if r['critical'] else ''))
        else:
            watch.append('«%s» از ویژگی‌های پررنگ داوطلب است، اما در این شغل کمک نمی‌کند.' % r['fa'])
    for r in sorted([x for x in ab.get('rows', []) if x['status'] == 'short'], key=lambda x: -x['weight'])[:top]:
        watch.append('توانایی «%s» پایین‌تر از سطح مورد نیاز این شغل برآورد شد.' % r['fa'])
    unmeasured = [r['fa'] for r in sorted(ab.get('unmeasured', []), key=lambda x: -x['weight']) if r['im'] >= 3][:5]
    return {'why': why[:top + 1], 'watch': watch[:top + 1], 'unmeasured': unmeasured}
