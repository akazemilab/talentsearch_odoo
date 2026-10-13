"""Major-family profiles (KK-PROFILE). Deterministic: same reference tables + same inputs = same JSON (hash recorded)."""
import csv
import hashlib
import json
import os
import re

from kk_text import key, norm

VERSION = 'KK-PROFILE-v0.1-2026-10-13'
HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, 'ref')
RIASEC = ('R', 'I', 'A', 'S', 'E', 'C')
PROJECT_RX = re.compile(key('پروژه') + '|' + key('پایان نامه') + '|' + key('کارورزی') + '|' + key('کارآموزی') + '|' + key('سمینار'))


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8-sig', newline='') as f:
        return [{k: (v or '').strip() for k, v in r.items()} for r in csv.DictReader(f)]


def weights(spec):
    """'math:0.6|physics:0.4' -> {'math':0.6,'physics':0.4}"""
    out = {}
    for part in (spec or '').split('|'):
        if ':' in part:
            k, v = part.split(':', 1)
            out[k.strip()] = float(v)
    return out


class Classifier:
    """Course name -> knowledge area by the longest matching keyword (keys compared without spaces/ZWNJ)."""

    def __init__(self, rows=None):
        rows = rows if rows is not None else read_csv(os.path.join(REF, 'course_keywords.csv'))
        self.rules = sorted(((key(r['keyword']), r['area']) for r in rows if r.get('keyword')),
                            key=lambda kv: (-len(kv[0]), kv[0]))

    def area(self, name):
        k = key(name)
        for kw, area in self.rules:
            if kw and kw in k:
                return area
        return None


def file_hash(paths):
    h = hashlib.sha256()
    for p in sorted(paths):
        if os.path.exists(p):
            h.update(p.encode())
            with open(p, 'rb') as f:
                h.update(f.read())
    return h.hexdigest()[:16]


def course_profile(courses, clf, know_rows):
    """courses: dicts with course, units_total, units_practice. Returns knowledge %, shares, subjects, unclassified."""
    know_sub = {r['code']: weights(r['subjects']) for r in know_rows}
    units, unclassified, total, practice, project = {}, [], 0.0, 0.0, 0.0
    for c in courses:
        u = float(c.get('units_total') or 0)
        if u <= 0:
            continue
        a = clf.area(c['course'])
        if a == 'general':
            continue
        total += u
        practice += float(c.get('units_practice') or 0)
        is_project = bool(PROJECT_RX.search(key(c['course'])))
        if is_project:
            project += u
        if a is None:
            if not is_project:
                unclassified.append(norm(c['course']))
            continue
        units[a] = units.get(a, 0.0) + u
    classified = sum(units.values())
    know = {a: round(100 * u / classified, 1) for a, u in sorted(units.items())} if classified else {}
    subj = {}
    for a, pct in know.items():
        for s, w in know_sub.get(a, {}).items():
            subj[s] = subj.get(s, 0.0) + pct * w
    st = sum(subj.values())
    subj = {s: round(v / st, 3) for s, v in sorted(subj.items())} if st else {}
    return {'knowledge': know, 'subjects': subj,
            'practice_share': round(practice / total, 3) if total else None,
            'project_share': round(project / total, 3) if total else None,
            'units_counted': total, 'units_classified': classified, 'unclassified': sorted(set(unclassified))}


def onet_interests(cache, soc_codes):
    """Mean O*NET occupational interest (1-7) over the family's occupations. Shape-tolerant reader."""
    occs = cache.get('occupations', cache) if isinstance(cache, dict) else {}
    acc, n, missing = {k: 0.0 for k in RIASEC}, 0, []
    for code in soc_codes:
        o = occs.get(code) if isinstance(occs, dict) else None
        oi = None
        if isinstance(o, dict):
            for fld in ('OI', 'oi', 'interests', 'riasec'):
                if isinstance(o.get(fld), dict):
                    oi = o[fld]
                    break
        if not oi:
            missing.append(code)
            continue
        names = {'R': ('R', 'Realistic'), 'I': ('I', 'Investigative'), 'A': ('A', 'Artistic'),
                 'S': ('S', 'Social'), 'E': ('E', 'Enterprising'), 'C': ('C', 'Conventional')}
        vals = {}
        for k, alts in names.items():
            v = next((oi[a] for a in alts if a in oi), None)
            if v is None:
                break
            vals[k] = float(v)
        if len(vals) < 6:
            missing.append(code)
            continue
        for k in RIASEC:
            acc[k] += vals[k]
        n += 1
    return ({k: round(acc[k] / n, 2) for k in RIASEC} if n else None), n, missing


def build(families, courses_by_family, family_soc, cache, overrides=None):
    clf, know_rows = Classifier(), read_csv(os.path.join(REF, 'knowledge.csv'))
    overrides = overrides or {}
    out, issues = [], []
    for f in families:
        fid = f['family_id']
        cp = course_profile(courses_by_family.get(fid, []), clf, know_rows)
        socs = [s for s in family_soc.get(fid, []) if s]
        ri, n, miss = onet_interests(cache, socs) if cache else (None, 0, socs)
        src = 'onet_v0' if ri else None
        if fid in overrides:
            ri, src = overrides[fid], 'expert_v1'
        if not ri:
            issues.append('%s: no interest profile (%d occupations, %d missing)' % (fid, len(socs), len(miss)))
        if not cp['knowledge']:
            issues.append('%s: no classified courses' % fid)
        if cp['unclassified']:
            issues.append('%s: %d unclassified course names' % (fid, len(cp['unclassified'])))
        out.append({'id': fid, 'name': f.get('name_fa'), 'groups': [g for g in f.get('groups', '').split('|') if g],
                    'riasec': ri, 'riasec_source': src, 'riasec_n_occupations': n, **cp})
    return {'version': VERSION, 'families': out, 'issues': issues}


def dump(obj, path):
    tmp = path + '.part'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)
