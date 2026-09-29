"""Talent Search - interactive talent inventory engine (TS-MATRIX-1.0).

Pure functions over plain data (no ORM), so golden tests run anywhere.

Source of the rules: the book "آموزش و پرورش برای استعداد و تیزهوشی" (Dr. Kazemi
Haghighi), section «تلفیق در مکتب تعاملی»: five basic abilities x fields, composite
rows, and the seven diagnosis levels. Scale score = sum of the 3 items / 15 x 100
(range 20-100); a composite is the plain mean of its scales; the "mean" column is
the mean of a row over the participant's fields.

Ties: the book reports fields that share the top score together. Here `best` holds
every key that is EXACTLY tied at the top; `near` holds keys within `gap` points
(default 10, about the standard error of a difference between two 3-item scales) so
the report can say "about equal" without merging them into the headline.
"""
import hashlib

ENGINE = 'TS-MATRIX-1.0'
SCALES = ['ANA', 'EXP', 'ACA', 'NOV', 'DUT']
INTEL = ['ANA', 'EXP', 'ACA']
ACTION = ['NOV', 'DUT']
COMPOSITES = {
    'TOT': SCALES,
    'INT': INTEL,
    'ACT': ACTION,
    'CRE': ['ANA', 'EXP', 'NOV'],
    'SCH': ['ACA', 'DUT'],
    'CRT': ['ANA', 'NOV'],
    'CRP': ['EXP', 'NOV'],
}
ALL_CODES = SCALES + list(COMPOSITES)
NAMES = {
    'ANA': 'هوش تحلیلی', 'EXP': 'هوش تجربی', 'ACA': 'هوش تحصیلی',
    'NOV': 'کنش نوسودمندی', 'DUT': 'کنش وظیفه‌مندی',
    'TOT': 'کل', 'INT': 'هوش', 'ACT': 'کنش', 'CRE': 'خلّاقیّت',
    'SCH': 'استعداد تحصیلی', 'CRT': 'خلّاقیّت نظری', 'CRP': 'خلّاقیّت عملی',
}
SHORT = {'ANA': 'تحلیلی', 'EXP': 'تجربی', 'ACA': 'تحصیلی', 'NOV': 'نوسودمندی', 'DUT': 'وظیفه‌مندی'}
ITEM_COUNT = 15
ITEMS_PER_SCALE = 3
FAST_SECONDS = 30
EPS = 1e-9


class ScoringError(ValueError):
    pass


def scale_of_item(index):
    """0-based item index -> scale code (item i belongs to scale (i-1) mod 5, 1-based)."""
    return SCALES[index % 5]


def _mean(values):
    return sum(values) / len(values)


def score_field(answers):
    if len(answers) != ITEM_COUNT:
        raise ScoringError('a field needs exactly %d answers, got %d' % (ITEM_COUNT, len(answers)))
    for i, v in enumerate(answers):
        if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 5:
            raise ScoringError('answer %d must be an integer 1-5, got %r' % (i + 1, v))
    scales = {}
    for k, code in enumerate(SCALES):
        chunk = [answers[i] for i in range(ITEM_COUNT) if i % 5 == k]
        scales[code] = sum(chunk) / (5.0 * len(chunk)) * 100.0
    comps = {code: _mean([scales[s] for s in members]) for code, members in COMPOSITES.items()}
    return scales, comps


def score_matrix(fields):
    """fields: [{'label': str, 'answers': [15 ints], 'seconds': int|None}]"""
    if not fields:
        raise ScoringError('no fields')
    labels = [f['label'] for f in fields]
    if len(set(labels)) != len(labels):
        raise ScoringError('duplicate field labels')
    out_fields, payload = [], []
    for seq, f in enumerate(fields, 1):
        scales, comps = score_field(f['answers'])
        secs = f.get('seconds')
        out_fields.append({
            'seq': seq, 'label': f['label'], 'scales': scales, 'composites': comps,
            'flags': {'straight': len(set(f['answers'])) == 1,
                      'fast': secs is not None and secs < FAST_SECONDS},
            'seconds': secs,
        })
        payload.append('%d:%s:%s' % (seq, f['label'], ''.join(str(v) for v in f['answers'])))
    mean = {}
    for code in ALL_CODES:
        src = 'scales' if code in SCALES else 'composites'
        mean[code] = _mean([of[src][code] for of in out_fields])
    input_hash = hashlib.md5('|'.join(payload).encode()).hexdigest()
    body = '|'.join('%s:%.9f' % (c, mean[c]) for c in ALL_CODES)
    output_hash = hashlib.md5((input_hash + '#' + body).encode()).hexdigest()
    return {'fields': out_fields, 'mean': mean, 'input_hash': input_hash,
            'output_hash': output_hash, 'engine': ENGINE}


# --------------------------------------------------------------- interpretation
def pick(pairs, gap, highest=True):
    """pairs [(key, value)] in display order -> exact-tie set and near set."""
    sign = 1 if highest else -1
    best = max(sign * v for _, v in pairs) * sign
    tied = [k for k, v in pairs if abs(v - best) <= EPS]
    near = [k for k, v in pairs if k not in tied and abs(v - best) <= gap + EPS]
    return {'best': tied, 'near': near, 'value': best}


def _first(pairs, highest=True):
    """Deterministic primary: best value, ties resolved by order (book's table order)."""
    sign = 1 if highest else -1
    top = max(sign * v for _, v in pairs)
    for k, v in pairs:
        if abs(sign * v - top) <= EPS:
            return k, v


def interpret(result, gap=10.0):
    fields = result['fields']
    mean = result['mean']
    labels = [f['label'] for f in fields]
    by = {f['label']: f for f in fields}
    n = len(fields)

    def cell(label, code):
        f = by[label]
        return f['scales'][code] if code in SCALES else f['composites'][code]

    out = {'engine': ENGINE, 'n_fields': n, 'gap': gap, 'labels': labels,
           'flagged': [f['label'] for f in fields if f['flags']['straight'] or f['flags']['fast']]}
    # level 1 - overall
    out['overall'] = {'score': mean['TOT']}
    # abilities inside one field (used by the single-field report and the per-field card)
    out['per_field'] = []
    for f in fields:
        ab = sorted(SCALES, key=lambda c: -f['scales'][c])
        it, its = _first([(c, f['scales'][c]) for c in INTEL])
        ac, acs = _first([(c, f['scales'][c]) for c in ACTION])
        out['per_field'].append({
            'label': f['label'], 'total': f['composites']['TOT'], 'order': ab,
            'intel': it, 'action': ac,
            'policy': '%s %s' % (SHORT[ac], SHORT[it]), 'policy_score': (its + acs) / 2,
        })
    if n < 2:
        return out
    # level 2 - brief
    ab_pick = pick([(c, mean[c]) for c in SCALES], gap)
    fl_pick = pick([(l, cell(l, 'TOT')) for l in labels], gap)
    out['brief'] = {'abilities': ab_pick['best'], 'abilities_near': ab_pick['near'], 'ability_score': ab_pick['value'],
                    'fields': fl_pick['best'], 'fields_near': fl_pick['near'], 'field_score': fl_pick['value'],
                    'score': (ab_pick['value'] + fl_pick['value']) / 2}
    # level 3 - composite
    out['composite'] = {}
    for key, code in (('intel', 'INT'), ('action', 'ACT')):
        p = pick([(l, cell(l, code)) for l in labels], gap)
        out['composite'][key] = {'fields': p['best'], 'near': p['near'], 'score': p['value']}
    # level 4 - focal
    fo = {}
    for key, members in (('intel', INTEL), ('action', ACTION)):
        cells = [((c, l), cell(l, c)) for c in members for l in labels]
        (c, l), v = _first(cells)
        tied = [k for k, x in cells if abs(x - v) <= EPS]
        fo[key] = {'ability': c, 'field': l, 'score': v, 'ties': [{'ability': a, 'field': b} for a, b in tied]}
    out['focal'] = fo
    # level 5 - detail
    counts = {c: 0 for c in SCALES}
    for pf in out['per_field']:
        counts[pf['intel']] += 1
        counts[pf['action']] += 1
    mi = max(counts[c] for c in INTEL)
    ma = max(counts[c] for c in ACTION)
    intel_mode = [c for c in INTEL if counts[c] == mi]
    action_mode = [c for c in ACTION if counts[c] == ma]
    union = set()
    for c in SCALES:
        union.update(pick([(l, cell(l, c)) for l in labels], gap)['best'])
    out['detail'] = {'counts': counts, 'intel_mode': intel_mode, 'action_mode': action_mode,
                     'combined': len(intel_mode) > 1 or len(action_mode) > 1,
                     'fields': [l for l in labels if l in union],
                     'best_by_scale': {c: pick([(l, cell(l, c)) for l in labels], gap)['best'] for c in SCALES}}
    # level 6 - talent types
    out['types'] = {}
    for code in ('CRE', 'SCH', 'CRT', 'CRP'):
        p = pick([(l, cell(l, code)) for l in labels], gap)
        out['types'][code] = {'fields': p['best'], 'near': p['near'], 'score': p['value']}
    # level 7 - weak
    wa = pick([(c, mean[c]) for c in SCALES], gap, highest=False)
    wf = pick([(l, cell(l, 'TOT')) for l in labels], gap, highest=False)
    out['weak'] = {'abilities': wa['best'], 'abilities_near': wa['near'], 'ability_score': wa['value'],
                   'fields': wf['best'], 'fields_near': wf['near'], 'field_score': wf['value']}
    # programs (names exactly as the book: تسریعی / غنی‌سازی / آموزش جبرانی / پرورش تقویّتی)
    top_ab, _ = _first([(c, mean[c]) for c in SCALES])
    w_field = wf['best'][0]
    w_ab = wa['best'][0]
    found = out['detail']['fields']
    out['programs'] = {
        'CRE': ['غنی‌سازی %s' % l for l in out['types']['CRE']['fields']],
        'SCH': ['تسریعی %s' % l for l in out['types']['SCH']['fields']],
        'CRT': ['غنی‌سازی تحلیلی %s' % l for l in out['types']['CRT']['fields']],
        'CRP': ['غنی‌سازی تجربی %s' % l for l in out['types']['CRP']['fields']],
        'compensatory': 'آموزش جبرانی %s با بهره‌گیری از %s' % (w_field, NAMES[top_ab]),
        'reinforcing': 'پرورش تقویّتی %s با استفاده از %s' % (NAMES[w_ab], '، '.join(found)),
    }
    return out
