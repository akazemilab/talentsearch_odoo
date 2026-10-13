"""onb3 sample reports («نمونه — داده‌های ساختگی»), one per kind, rendered with the real report templates.

Everything is built in memory from fixed synthetic answers, scored by the real engines (the questionnaire engine, the
talent matrix engine, the job-fit engine); nothing is stored, so no person, account, attempt or panel exists behind a
sample and nothing can be counted, billed or shown anywhere else. The records the templates read are `new()` records (no
database row). The engines run once per database, kind and day (a per-process cache of plain values; the public pages
cannot make the server score anything on each request). The public sample of a counseling panel carries the
participant's own texts only: the counselor guide and the talk points are never put into it.
"""
import copy
import json
from datetime import date

from odoo import api, models

from odoo.addons.ts_assessment.models.engine import contract_from_version, score as engine_score

# the level each factor of a questionnaire is answered at (cycled): a calm, mixed profile, never extreme
PATTERN = (3, 4, 2, 3, 4, 3, 2, 3)
TALENT_FIELDS = (('ریاضی', (4, 4, 5, 4, 3, 4, 4, 5, 3, 4, 4, 3, 4, 5, 4)),
                 ('نقاشی', (3, 2, 3, 4, 5, 4, 3, 2, 4, 5, 3, 4, 2, 3, 4)),
                 ('برنامه‌نویسی', (4, 5, 4, 3, 4, 5, 4, 4, 5, 3, 4, 4, 5, 4, 3)),
                 ('زیست‌شناسی', (3, 3, 2, 3, 3, 4, 2, 3, 3, 2, 3, 3, 4, 3, 2)))
HR_FACET_LEVELS = (3.9, 3.4, 4.2, 2.8, 3.6, 4.0, 3.1, 3.7, 2.9, 4.3, 3.5, 3.2)
HR_ABILITIES = {'Inductive Reasoning': 64, 'Information Ordering': 52, 'Deductive Reasoning': 71}
SAMPLE_NAMES = {'clinic': 'مریم نمونه', 'solo': 'مریم نمونه', 'school': 'آرمان نمونه', 'hr': 'نگار نمونه'}
STAFF_ONLY = ('therapist_text', 'talk_points')
_CACHE = {}         # (dbname, kind, day) -> plain values computed by the engines (no records, no cursor)


class TsOnbSample(models.AbstractModel):
    _name = 'ts.onb.sample'
    _description = 'Talent Search synthetic sample reports (onb3, nothing stored)'

    @api.model
    def _likert_answers(self, version):
        """{item id: value} for every active item: each factor at the PATTERN level, reverse items mirrored."""
        lo, hi = version.scale_min or 1, version.scale_max or 5
        factors = version.factor_ids.sorted(lambda f: (f.sequence, f.id))
        level = {f.id: PATTERN[i % len(PATTERN)] for i, f in enumerate(factors)}
        out = {}
        for n, it in enumerate(version.item_ids.filtered(lambda i: not i.disabled).sorted(lambda i: (i.sequence, i.id))):
            v = max(lo, min(hi, level.get(it.factor_id.id, 3) + (1 if n % 7 == 3 else 0) - (1 if n % 11 == 5 else 0)))
            if getattr(it, 'reverse', False):
                v = hi + lo - v
            out[it.id] = v
        return out

    @api.model
    def _cached(self, kind, build):
        """The plain values of `kind` for today, computed once by `build()` (None is not cached)."""
        key = (self.env.cr.dbname, kind, date.today())
        if key not in _CACHE:
            for k in [k for k in _CACHE if k[0] == key[0] and k[1] == kind]:
                _CACHE.pop(k, None)              # yesterday's values of this kind
            val = build()
            if val is None:
                return None
            _CACHE[key] = val
        return copy.deepcopy(_CACHE[key])

    @api.model
    def _result_values(self, version):
        """Plain values of the result rows of one questionnaire version (the real engine and the band texts at hand)."""
        out = engine_score(contract_from_version(version), self._likert_answers(version))
        factors = {f.code: f for f in version.factor_ids}
        vals = []
        for r in out['results']:
            f = factors[r['factor']]
            band = f.band_ids.filtered(lambda b: b.band == r['band'])[:1]
            vals.append({'factor_id': f.id, 'score': r['score'], 'band': r['band'], 'band_id': band.id,
                         'item_count': r['item_count'], 'answered_count': r['answered'], 'raw_total': r['raw_total'],
                         'client_text': band.client_text, 'therapist_text': band.therapist_text,
                         'content_version': band.content_version, 'content_format': band.content_format or 'book',
                         'talk_points': band.talk_points or False, 'definition': f.definition or False})
        return vals

    @api.model
    def _results(self, version, values=None, public=False):
        """In-memory result rows (new() records) of one questionnaire version, on an in-memory attempt of that version
        (the participant's report blocks read the attempt). `public`: without the counselor guide and the talk points."""
        values = values if values is not None else self._result_values(version)
        at = self.env['ts.attempt'].new({'instrument_id': version.instrument_id.id, 'version_id': version.id,
                                         'state': 'done', 'released': True, 'name': 'نمونه'})
        R = self.env['ts.attempt.result']
        rows = R.browse()
        for v in values:
            v = dict(v, attempt_id=at)
            if public:
                v.update({k: False for k in STAFF_ONLY})
            rows |= R.new(v)
        return rows.sorted(lambda r: (r.factor_id.sequence, r.factor_id.id))

    # ------------------------------------------------------------------ per kind
    @api.model
    def _clinic_values(self):
        """(battery id, [(instrument id, version id, row values)]) of BAT-INTAKE-1 (questionnaire parts only), or None."""
        b = self.env['ts.battery'].sudo().search([('code', '=', 'BAT-INTAKE-1'), ('state', '=', 'published')], limit=1)
        if not b:
            return None
        parts = []
        for line in b.ts_lines():
            inst = line.instrument_id.sudo()
            v = inst.current_version_id
            if not v or ('mode' in v._fields and v.mode not in (False, 'single')):
                continue
            try:
                parts.append((inst.id, v.id, self._result_values(v)))
            except Exception:       # noqa: BLE001 - a part that cannot be scored is left out of the sample
                continue
        return (b.id, parts) if parts else None

    @api.model
    def ts_clinic(self, public=False):
        """{'battery', 'sections': [{'inst', 'results'}]} of BAT-INTAKE-1. `public`: participant texts only."""
        cached = self._cached('clinic', self._clinic_values)
        if not cached:
            return None
        bid, parts = cached
        I, V = self.env['ts.instrument'].sudo(), self.env['ts.instrument.version'].sudo()
        sections = [{'inst': I.browse(iid), 'results': self._results(V.browse(vid), values=vals, public=public)}
                    for iid, vid, vals in parts]
        return {'battery': self.env['ts.battery'].sudo().browse(bid), 'sections': sections}

    @api.model
    def _school_values(self):
        from odoo.addons.ts_talent.models import engine_matrix as EM
        inst = self.env['ts.instrument'].sudo().search([('code', '=', 'TALENT-INV-15'), ('state', '=', 'published')], limit=1)
        v = inst.current_version_id if inst else None
        if not v:
            return None
        data = [{'label': label, 'answers': list(ans[:EM.ITEM_COUNT]), 'seconds': 120} for label, ans in TALENT_FIELDS]
        result = EM.score_matrix(data)
        profile = dict(result, interpretation=EM.interpret(result, gap=v.noise_gap))
        return inst.id, v.id, json.dumps(profile, ensure_ascii=False)

    @api.model
    def ts_school(self):
        """(attempt, workspace) new() records for ts_talent's report_ctx (org view), or None. The talent report has no
        counselor-only text (no guide, no talk points): the school sees what the student sees, without raw answers."""
        cached = self._cached('school', self._school_values)
        if not cached:
            return None
        iid, vid, profile_json = cached
        inst, v = self.env['ts.instrument'].sudo().browse(iid), self.env['ts.instrument.version'].sudo().browse(vid)
        person = self.env['res.partner'].new({'name': SAMPLE_NAMES['school']})
        at = self.env['ts.attempt'].new({'instrument_id': inst.id, 'version_id': v.id, 'state': 'done', 'source': 'web',
                                         'released': True, 'profile_json': profile_json,
                                         'person_id': person.id, 'name': 'نمونه'})
        ws = self.env['ts.workspace'].new({'name': 'مدرسهٔ نمونه', 'purpose': 'education'})
        return at, ws

    @api.model
    def _hr_values(self):
        from odoo.addons.ts_onet.models import jobfit as J
        from .onb3 import SAMPLE_OCCUPATIONS
        Occ = self.env['ts.onet.occupation'].sudo()
        occ = Occ.browse()
        for code in SAMPLE_OCCUPATIONS:
            occ = Occ.search([('code', '=', code)], limit=1)
            if occ:
                break
        if not occ:
            return None
        facets = {f: HR_FACET_LEVELS[i % len(HR_FACET_LEVELS)] for i, f in enumerate(J.FACETS)}
        return occ.id, occ.ts_jobfit(facets=facets, abilities=dict(HR_ABILITIES))

    @api.model
    def ts_hr(self):
        """{'res', 'r', 'occupation'} for ts_hire.candidate_fit: the job fit of a synthetic candidate for «کارشناس فروش».
        The employer's own view (levels and the fit summary); no participant text is in it."""
        from odoo.addons.ts_onet.models import jobfit as J
        cached = self._cached('hr', self._hr_values)
        if not cached:
            return None
        occ_id, res = cached
        occ = self.env['ts.onet.occupation'].sudo().browse(occ_id)
        r = {'a': None, 'level': 'summary', 'res': res, 'band': res.get('band'), 'band_fa': J.BAND_FA[res.get('band')],
             'ws_band': res.get('ws') and res['ws'].get('band'), 'ab_band': res['ab'].get('band'),
             'explain': J.explain(res), 'flags': [], 'state': 'تکمیل‌شده', 'progress': None, 'decision': '', 'complete': True}
        return {'res': res, 'r': r, 'occupation': occ}

    @api.model
    def ts_kind_sample(self, kind, public=False):
        """{'kind', 'name', ...} with the kind's sample, or None when its instruments are not published. `public`: the
        audience pages' sample (participant-level texts only)."""
        kind = 'clinic' if kind == 'solo' else kind
        if kind == 'clinic':
            d = self.ts_clinic(public=public)
        elif kind == 'school':
            pair = self.ts_school()
            d = {'attempt': pair[0], 'ws': pair[1]} if pair else None
        elif kind == 'hr':
            d = self.ts_hr()
        else:
            d = None
        if not d:
            return None
        d.update(kind=kind, who=SAMPLE_NAMES[kind])
        return d
