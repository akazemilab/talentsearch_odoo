"""KK-MATCH: student -> Iranian major families. Pure and deterministic (no I/O, no randomness, no learning).

Student input (dict):
  group    'riazi' | 'tajrobi' | 'ensani' | 'honar' | 'zaban'      konkur group the student sits
  riasec   {'R':x,'I':x,'A':x,'S':x,'E':x,'C':x}                   any scale (Interest Profiler raw 0-40)
  liked    {subject_code: 1..5}                                      optional
  grades   {subject_code: percent}                                   optional; mock-konkur percent may be < 0
  exclude  [family_id, ...]                                          optional (counselor's practical filter)
Profile (one major family): see kk_profile.build(); uses 'id', 'name', 'groups', 'riasec', 'subjects'.
"""
import math

VERSION = 'KK-MATCH-v0.1-2026-10-13'
RIASEC = ('R', 'I', 'A', 'S', 'E', 'C')
W_INTEREST, W_SUBJECT = 0.6, 0.4          # hypotheses; the pilot adjusts them (new version string when changed)


def pearson(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    da, db = [x - ma for x in a], [y - mb for y in b]
    va, vb = sum(x * x for x in da), sum(y * y for y in db)
    if va <= 1e-12 or vb <= 1e-12:
        return None                        # flat profile: shape undefined, do not invent a fit
    return sum(x * y for x, y in zip(da, db)) / math.sqrt(va * vb)


def interest_fit(person, major):
    r = pearson([float(person[k]) for k in RIASEC], [float(major[k]) for k in RIASEC])
    return None if r is None else round(50 * (1 + r), 1)


def subject_strengths(liked, grades):
    """Per subject 0..1. Liking: (x-1)/4. Grades: within-student z, 0.5 + z/4 clipped (relative strength only)."""
    out = {}
    vals = [float(v) for v in (grades or {}).values()]
    gz = {}
    if len(vals) >= 3:
        m = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals))
        for s, v in grades.items():
            gz[s] = 0.5 if sd < 1e-9 else min(1.0, max(0.0, 0.5 + (float(v) - m) / sd / 4))
    for s in set(liked or {}) | set(gz):
        parts = []
        if s in (liked or {}):
            parts.append(min(1.0, max(0.0, (float(liked[s]) - 1) / 4)))
        if s in gz:
            parts.append(gz[s])
        out[s] = sum(parts) / len(parts)
    return out, gz


def subject_fit(strength, weights):
    """Weighted mean over the subjects the student has data for; None when the major's weight there is < 30%."""
    have = {s: w for s, w in (weights or {}).items() if s in strength and w > 0}
    tot = sum(w for w in (weights or {}).values() if w > 0)
    if not have or tot <= 0 or sum(have.values()) / tot < 0.3:
        return None
    return round(100 * sum(strength[s] * w for s, w in have.items()) / sum(have.values()), 1)


def match(student, profiles, top=None):
    strength, gz = subject_strengths(student.get('liked'), student.get('grades'))
    grp, excl = student.get('group'), set(student.get('exclude') or ())
    rows = []
    for p in profiles:
        if p['id'] in excl or (grp and p.get('groups') and grp not in p['groups']):
            continue
        fi = interest_fit(student['riasec'], p['riasec']) if p.get('riasec') else None
        fs = subject_fit(strength, p.get('subjects'))
        parts = [(W_INTEREST, fi), (W_SUBJECT, fs)]
        used = [(w, v) for w, v in parts if v is not None]
        if not used:
            continue
        fit = round(sum(w * v for w, v in used) / sum(w for w, _ in used), 1)
        rows.append({'id': p['id'], 'name': p.get('name'), 'fit': fit, 'interest': fi, 'subject': fs,
                     'reasons': reasons(student, p, strength, gz)})
    rows.sort(key=lambda r: (-r['fit'], r['id']))
    return {'version': VERSION, 'n': len(rows), 'rows': rows[:top] if top else rows}


def reasons(student, p, strength, gz):
    out = []
    if p.get('riasec'):
        top_p = sorted(RIASEC, key=lambda k: (-float(student['riasec'][k]), k))[:2]
        top_m = sorted(RIASEC, key=lambda k: (-float(p['riasec'][k]), k))[:3]
        shared = [k for k in top_p if k in top_m]
        if shared:
            out.append('interest:' + ''.join(shared))
    w = p.get('subjects') or {}
    for s in sorted(w, key=lambda s: (-w[s], s))[:3]:
        if s in strength and strength[s] >= 0.7:
            out.append('subject+:' + s)
        liked = (student.get('liked') or {}).get(s)
        if s in gz and gz[s] >= 0.7 and liked is not None and liked <= 2:
            out.append('check:' + s + ':strong-grade-low-liking')
        if liked is not None and liked >= 4 and s in gz and gz[s] <= 0.3:
            out.append('check:' + s + ':liked-weak-grade')
    return out
