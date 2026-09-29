"""Talent Search scoring engine - parity with the source engine
`S09-V3.0-multi-inventory` (old sepehrtherapy.ir Odoo, server action 1290):

* only active (non-disabled) items count; every active item needs exactly one
  answer; answers are integers in [scale_min, scale_max] (1-5), otherwise NO score;
* reverse items score (scale_min + scale_max) - x  (= 6 - x on the 1-5 scale);
* factor score = average of scored values of that factor's active items;
* the factor score must fall in exactly one band, bounds inclusive;
* every factor with active items must be a scored factor with three bands.

Pure functions over plain data, so golden tests can run without the ORM.
"""
import hashlib
import json

ENGINE_VERSION = 'S09-V3.0-multi-inventory'


class ScoringError(ValueError):
    pass


def score(contract, answers):
    """contract: {'scale_min', 'scale_max', 'factors': [{'code', 'bands': [{'band','min','max'}]}],
                  'items': [{'id', 'factor', 'reverse', 'disabled'}]}
    answers: {item_id: int}
    returns {'results': [{'factor','score','band','item_count','answered','raw_total'}],
             'input_hash', 'output_hash'}"""
    lo, hi = contract['scale_min'], contract['scale_max']
    active = [i for i in contract['items'] if not i['disabled']]
    if not active:
        raise ScoringError('no active items')
    active_ids = {i['id'] for i in active}
    if set(answers) != active_ids:
        missing = sorted(active_ids - set(answers))
        extra = sorted(set(answers) - active_ids)
        raise ScoringError('answer coverage mismatch: missing=%s extra=%s' % (missing[:10], extra[:10]))
    for iid, val in answers.items():
        if not isinstance(val, int) or isinstance(val, bool) or not lo <= val <= hi:
            raise ScoringError('answer for item %s must be an integer %d-%d, got %r' % (iid, lo, hi, val))
    by_factor = {}
    for it in active:
        by_factor.setdefault(it['factor'], []).append(it)
    factors = {f['code']: f for f in contract['factors']}
    unscored = [code for code in by_factor if code not in factors or not factors[code].get('bands')]
    if unscored:
        raise ScoringError('factors with active items but no scoring rule: %s' % unscored)
    payload = '|'.join('%s:%s:%d' % (it['id'], answers[it['id']], 1 if it['reverse'] else 0)
                       for it in sorted(active, key=lambda x: x['id']))
    input_hash = hashlib.md5(payload.encode()).hexdigest()
    results = []
    for code in sorted(by_factor):
        items = by_factor[code]
        raw = [answers[i['id']] for i in items]
        scored = [(lo + hi - answers[i['id']]) if i['reverse'] else answers[i['id']] for i in items]
        value = sum(scored) / len(scored)
        hits = [b for b in factors[code]['bands'] if b['min'] <= value <= b['max']]
        if len(hits) != 1:
            raise ScoringError('factor %s score %.6f matches %d bands' % (code, value, len(hits)))
        results.append({'factor': code, 'score': value, 'band': hits[0]['band'], 'item_count': len(items),
                        'answered': len(items), 'raw_total': float(sum(raw))})
    out = '|'.join('%s|%.12f|%s' % (r['factor'], r['score'], r['band']) for r in results)
    output_hash = hashlib.md5((input_hash + '#' + out).encode()).hexdigest()
    return {'results': results, 'input_hash': input_hash, 'output_hash': output_hash, 'engine': ENGINE_VERSION}


def contract_from_version(version):
    """Serialise an ts.instrument.version into the engine's plain structure."""
    return {
        'scale_min': version.scale_min,
        'scale_max': version.scale_max,
        'factors': [{'code': f.code, 'bands': [{'band': b.band, 'min': b.min_score, 'max': b.max_score}
                                               for b in f.band_ids]}
                    for f in version.factor_ids if f.scored],
        'items': [{'id': i.id, 'factor': i.factor_id.code, 'reverse': i.reverse, 'disabled': i.disabled}
                  for i in version.item_ids],
    }


def contract_fingerprint(contract):
    return hashlib.md5(json.dumps(contract, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
