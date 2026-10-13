#!/usr/bin/env python3
"""Content v2, step 1: write one editable skeleton per instrument (pure Python, no Odoo).

    python3 tools/content/ts_content_export.py            # the 33 active source instruments
    python3 tools/content/ts_content_export.py --talent   # also TALENT-INV-15
    python3 tools/content/ts_content_export.py --only inventory_012 --dry-run

Source instruments: addons/ts_assessment/data/source/psy_source.json + workbook_meta.json, selected exactly as
ts_assessment/models/loader.py (_ts_load_source) does: one active contract per instrument (else retired, skipped),
a factor's rule only when it belongs to that contract, threshold rules of the rule = bands, keyed by
x_band.lower() (low / medium / high); a factor without bands is not scored and is left out. Items as stored by the
loader (same order), disabled items left out (they are never asked or scored).
Every new-text field is empty; ref_* fields hold today's text: ref_definition and ref_participant_shown go through
textfmt.split_interpretation (the display path of ts.attempt.result.client_sections), ref_*_raw are the book texts.
A target file whose status is not "draft" is never overwritten.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASM = os.path.join(ROOT, 'addons', 'ts_assessment')
TAL = os.path.join(ROOT, 'addons', 'ts_talent')
SCHEMA = 'ts-content/2'
CONTENT_VERSION = 'TS-CONTENT-2.0'
REGISTER = {'adult': 'shoma', 'adolescent': 'tu', 'child': 'parent'}
BAND_ORDER = ('low', 'medium', 'high')


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


textfmt = _load_module('ts_textfmt', os.path.join(ASM, 'models', 'textfmt.py'))


def _constants(path, names):
    """Module-level literal constants of a source file (the Odoo modules cannot be imported without Odoo)."""
    tree = ast.parse(open(path, encoding='utf-8').read())
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in names:
                out[node.targets[0].id] = ast.literal_eval(node.value)
    missing = set(names) - set(out)
    if missing:
        raise SystemExit('constants not found in %s: %s' % (path, ', '.join(sorted(missing))))
    return out


def _m2o(v):
    return v[0] if isinstance(v, (list, tuple)) and v else (v or False)


def _fa(s):
    return str(s).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))


# ------------------------------------------------------------------ the loader's selection (plain data)
def source_instruments():
    src = json.load(open(os.path.join(ASM, 'data', 'source', 'psy_source.json'), encoding='utf-8'))
    meta = json.load(open(os.path.join(ASM, 'data', 'source', 'workbook_meta.json'), encoding='utf-8'))
    A = {a['id']: a for a in src['x_psy_assessment']}
    Q = {q['id']: q for q in src['survey.question']}
    contracts = {}
    for c in src['x_psy_scoring_contract']:
        contracts.setdefault(_m2o(c['x_assessment_id']), []).append(c)
    rules_by_factor = {_m2o(r['x_factor_id']): r for r in src['x_psy_factor_scoring_rule']}
    bands_by_rule = {}
    for t in src['x_psy_factor_threshold_rule']:
        bands_by_rule.setdefault(_m2o(t['x_rule_id']), []).append(t)
    factors_by_asm = {}
    for f in src['x_psy_factor']:
        factors_by_asm.setdefault(_m2o(f['x_assessment_id']), []).append(f)
    items_by_factor = {}
    for it in src['x_psy_assessment_item']:
        items_by_factor.setdefault(_m2o(it['x_factor_id']), []).append(it)

    out = []
    for aid, a in sorted(A.items(), key=lambda kv: kv[1]['x_code']):
        m = meta.get(a['x_code'], {})
        active = [c for c in contracts.get(aid, []) if c.get('x_active')]
        contract = active[0] if len(active) == 1 else None
        factors = []
        for f in sorted(factors_by_asm.get(aid, []), key=lambda x: (x['x_code'], x['id'])):
            rule = rules_by_factor.get(f['id'])
            if rule and contract and _m2o(rule['x_contract_id']) != contract['id']:
                rule = None
            bands = sorted(bands_by_rule.get(rule['id'], []) if rule else [], key=lambda b: b['x_min_score'])
            items = sorted(items_by_factor.get(f['id'], []),
                           key=lambda i: (i['x_sequence'], int(i['x_source_question_id']), i['id']))
            factors.append({'code': f['x_code'], 'name': f['x_name'], 'bands': bands, 'items': [
                {'qid': int(i['x_source_question_id']), 'text': (Q[_m2o(i['x_question_id'])]['title'] or '').strip(),
                 'rev': bool(i['x_reverse']), 'dis': bool(i['x_disabled'])} for i in items]})
        out.append({'code': a['x_code'], 'name': a['x_name'], 'meta': m, 'contract': contract, 'factors': factors})
    return out


def _title(name, all_names):
    """ts.instrument._compute_title: the name people see (no trailing item count, TITLE_SPELLING)."""
    spelling = _constants(os.path.join(ASM, 'models', 'instrument.py'), ['TITLE_SPELLING'])['TITLE_SPELLING']

    def base_of(n):
        return re.sub(r'\s*-\s*\d+\s*$', '', n or '').strip()
    base = base_of(name)
    m = re.search(r'-\s*(\d+)\s*$', name or '')
    dup = m and any(base_of(o) == base for o in all_names if o != name)
    shown = spelling.get(base, base)
    return '%s (%s پرسش)' % (shown, _fa(m.group(1))) if dup else shown


def _intro(inst, scored_names):
    """The loader's intended_use for this instrument (what «کاربرد» shows today)."""
    L = _constants(os.path.join(ASM, 'models', 'loader.py'), ['EMPLOYMENT_CATEGORIES'])
    cat, aud = inst['meta'].get('category'), inst['meta'].get('audience') or 'adult'
    if not (cat and scored_names):
        return ''
    who = ('این پرسشنامه را والد یا مراقب دربارهٔ کودک تکمیل می‌کند.' if aud == 'child' else
           'نوجوان با اطلاع و رضایت ولی پاسخ می‌دهد.' if aud == 'adolescent' else
           'پاسخ‌دهنده خود شرکت‌کننده است.')
    names = '، '.join(scored_names)
    if aud == 'adult' and cat in L['EMPLOYMENT_CATEGORIES']:
        return ('کاربرد: خودشناسی و گفت‌وگوی مشاوره‌ای در حوزهٔ «%s»؛ در پنل استخدامی، فقط با رضایت شرکت‌کننده '
                'و به‌صورت سطح هر عامل، به‌عنوان یکی از ورودی‌های گفت‌وگوی شغلی. این سنجه %s عامل را توصیف می‌کند: %s. %s '
                'این سنجه برای تشخیص به کار نمی‌رود و به‌تنهایی مبنای تصمیم استخدامی نیست.'
                % (cat, _fa(len(scored_names)), names, who))
    return ('کاربرد: خودشناسی و گفت‌وگوی مشاوره‌ای در حوزهٔ «%s». این سنجه %s عامل را توصیف می‌کند: %s. %s '
            'این سنجه برای تشخیص یا تصمیم استخدامی به کار نمی‌رود.' % (cat, _fa(len(scored_names)), names, who))


def _definition(bands):
    """ts_instrument_loader._ts_create_version: the DEF_HEADING section of the first band's client text."""
    if not bands:
        return ''
    for head, body in textfmt.split_interpretation(bands[0].get('x_client_text') or ''):
        if head == textfmt.DEF_HEADING:
            return body
    return ''


def _shown(text):
    """What the participant reads under the factor today, without the definition (kept in ref_definition)."""
    parts = []
    for head, body in textfmt.split_interpretation(text, participant=True):
        if head == textfmt.DEF_HEADING:
            continue
        parts.append(body if head in (None, textfmt.PARTICIPANT_HEADING) else '%s:\n%s' % (head, body))
    return '\n\n'.join(parts)


def _range(b):
    return '%.2f–%.2f' % (b['x_min_score'], b['x_max_score'])


def skeleton(inst, all_names):
    scored = [f for f in inst['factors'] if f['bands']]
    factors = []
    for f in scored:
        bands = {}
        for b in f['bands']:
            key = b['x_band'].lower()
            if key in bands:
                raise SystemExit('%s %s: two %s bands' % (inst['code'], f['code'], key))
            client, therapist = b.get('x_client_text') or '', b.get('x_therapist_text') or ''
            bands[key] = {'ref_range': _range(b), 'participant': '', 'counselor': '', 'talk_points': [],
                          'ref_participant_shown': _shown(client),
                          'ref_participant_raw': client, 'ref_counselor_raw': therapist}
        factors.append({'code': f['code'], 'name': '', 'ref_name': f['name'], 'definition': '',
                        'ref_definition': _definition(f['bands']),
                        'ref_items': [{'qid': i['qid'], 'text': i['text'], 'reverse': i['rev']}
                                      for i in f['items'] if not i['dis']],
                        'bands': {k: bands[k] for k in sorted(bands, key=lambda k: BAND_ORDER.index(k)
                                                              if k in BAND_ORDER else 99)}})
    aud = inst['meta'].get('audience') or 'adult'
    return {'schema': SCHEMA, 'instrument': inst['code'], 'content_version': CONTENT_VERSION, 'status': 'draft',
            'approved_by': '', 'approved_at': '', 'register': REGISTER[aud], 'summary': '',
            'ref': {'name': _title(inst['name'], all_names), 'book_name': inst['name'], 'audience': aud,
                    'category': inst['meta'].get('category') or '', 'contract': inst['contract']['x_version'],
                    'intro': _intro(inst, [f['name'] for f in scored])},
            'factors': factors}


# ------------------------------------------------------------------ TALENT-INV-15
def talent_skeleton():
    items = json.load(open(os.path.join(TAL, 'data', 'talent_items.json'), encoding='utf-8'))
    texts = json.load(open(os.path.join(TAL, 'data', 'talent_texts.json'), encoding='utf-8'))
    em = vars(_load_module('ts_engine_matrix', os.path.join(TAL, 'models', 'engine_matrix.py')))  # pure, no ORM
    rp = _constants(os.path.join(TAL, 'models', 'report.py'), ['PLAIN', 'PROGRAM_PLAIN', 'LEVEL_GLOSS'])
    ld = _constants(os.path.join(TAL, 'models', 'loader.py'),
                    ['CODE', 'CONTRACT_VERSION', 'INTENDED_USE', 'INTENDED_USE_TU', 'FIELD_GUIDANCE'])
    scales = em['SCALES']
    # the seven book levels of report.levels(); their titles are fixed, their lines are computed per result
    level_titles = [('overall', 'کلّی'), ('brief', 'اجمالی'), ('composite', 'ترکیبی'), ('focal', 'کانونی'),
                    ('detail', 'تفصیلی'), ('types', 'نوع استعداد'), ('weak', 'استعداد ضعیف')]
    return {
        'schema': SCHEMA, 'instrument': ld['CODE'], 'content_version': CONTENT_VERSION, 'status': 'draft',
        'approved_by': '', 'approved_at': '', 'register': 'shoma', 'summary': '',
        'ref': {'name': 'فهرست تعاملی استعداد', 'audience': 'adult', 'category': 'استعدادیابی',
                'contract': ld['CONTRACT_VERSION'], 'intro': ld['INTENDED_USE'], 'intro_tu': ld['INTENDED_USE_TU'],
                'source': texts.get('source', '')},
        'scales': [{'code': c, 'name': '', 'ref_name': em['NAMES'][c], 'ref_short': em['SHORT'][c],
                    'definition': '', 'ref_definition': texts['scales'][c]['definition'],
                    'ref_line': texts['scales'][c].get('line', ''),
                    'plain': '', 'ref_plain': rp['PLAIN'].get(c, ''),
                    'ref_items': [i + 1 for i in range(len(items)) if i % len(scales) == scales.index(c)]}
                   for c in scales],
        'composites': [{'code': c, 'parts': parts, 'name': '', 'ref_name': em['NAMES'][c],
                        'definition': '', 'ref_definition': (texts['composites'].get(c) or {}).get('definition', ''),
                        'ref_line': (texts['composites'].get(c) or {}).get('line', '')}
                       for c, parts in em['COMPOSITES'].items()],
        'levels': [{'key': k, 'title': '', 'ref_title': t, 'gloss': '', 'ref_gloss': rp['LEVEL_GLOSS'].get(k, '')}
                   for k, t in level_titles],
        'statements': [{'n': n + 1, 'scale': scales[n % len(scales)], 'text': '', 'ref_text': s}
                       for n, s in enumerate(items)],
        'glosses': {
            'field_guidance': {'text': '', 'ref_text': ld['FIELD_GUIDANCE']},
            'programs': [{'prefix': p, 'text': '', 'ref_text': t} for p, t in rp['PROGRAM_PLAIN']],
            'quotes': [{'key': k, 'ref_line': q.get('line', ''), 'ref_text': q.get('text', '')}
                       for k, q in texts.get('quotes', {}).items()],
        },
    }


# ------------------------------------------------------------------ writing
def write(path, data, dry):
    if os.path.exists(path):
        try:
            old = json.load(open(path, encoding='utf-8'))
        except ValueError:
            raise SystemExit('REFUSED %s: unreadable JSON (not overwritten)' % path)
        if old.get('status') != 'draft':
            print('REFUSED %s: status %r is not "draft"' % (os.path.relpath(path, ROOT), old.get('status')))
            return False
    if not dry:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
            fh.write('\n')
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--talent', action='store_true', help='also write TALENT-INV-15')
    ap.add_argument('--only', nargs='*', help='instrument codes (default: every active one)')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    insts = source_instruments()
    all_names = [i['name'] for i in insts]
    active = [i for i in insts if i['contract']]
    skipped = [i['code'] for i in insts if not i['contract']]
    if args.only:
        active = [i for i in active if i['code'] in args.only]
    out_dir = os.path.join(ASM, 'data', 'content_v2')
    print('%-15s %-9s %5s %7s %5s %s' % ('code', 'register', 'items', 'factors', 'bands', 'sha'))
    t_items = t_factors = t_bands = refused = 0
    for inst in active:
        sk = skeleton(inst, all_names)
        n_items = sum(len(f['ref_items']) for f in sk['factors'])
        n_bands = sum(len(f['bands']) for f in sk['factors'])
        ok = write(os.path.join(out_dir, '%s.json' % inst['code']), sk, args.dry_run)
        refused += not ok
        t_items, t_factors, t_bands = t_items + n_items, t_factors + len(sk['factors']), t_bands + n_bands
        sha = hashlib.sha1(json.dumps(sk, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:8]
        print('%-15s %-9s %5d %7d %5d %s' % (inst['code'], sk['register'], n_items, len(sk['factors']), n_bands, sha))
    print('%-15s %-9s %5d %7d %5d  (%d instruments; retired, no active contract: %s)'
          % ('TOTAL', '', t_items, t_factors, t_bands, len(active), ', '.join(skipped) or '-'))
    if args.talent:
        sk = talent_skeleton()
        ok = write(os.path.join(TAL, 'data', 'content_v2', '%s.json' % sk['instrument']), sk, args.dry_run)
        refused += not ok
        print('%-15s %-9s %5d %7s %5s  (scales %d, composites %d, levels %d, programs %d)' % (
            sk['instrument'], sk['register'], len(sk['statements']), '-', '-', len(sk['scales']),
            len(sk['composites']), len(sk['levels']), len(sk['glosses']['programs'])))
    if refused:
        print('%d file(s) refused (status not draft)' % refused)
    return 1 if refused else 0


if __name__ == '__main__':
    sys.exit(main())
