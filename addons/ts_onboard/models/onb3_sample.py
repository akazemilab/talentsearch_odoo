"""onb3 sample reports («نمونه — داده‌های ساختگی»), one per kind, rendered with the real report templates.

Everything is built in memory on each request from fixed synthetic answers, scored by the real engines (the questionnaire
engine, the talent matrix engine, the job-fit engine); nothing is stored, so no person, account, attempt or panel exists
behind a sample and nothing can be counted, billed or shown anywhere else. The records the templates read are `new()`
records (no database row).
"""
import json

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
    def _results(self, version):
        """In-memory result rows of one questionnaire version (the real engine and the band texts at hand)."""
        out = engine_score(contract_from_version(version), self._likert_answers(version))
        factors = {f.code: f for f in version.factor_ids}
        R = self.env['ts.attempt.result']
        rows = R.browse()
        for r in out['results']:
            f = factors[r['factor']]
            band = f.band_ids.filtered(lambda b: b.band == r['band'])[:1]
            rows |= R.new({'factor_id': f.id, 'score': r['score'], 'band': r['band'], 'band_id': band.id,
                           'item_count': r['item_count'], 'answered_count': r['answered'], 'raw_total': r['raw_total'],
                           'client_text': band.client_text, 'therapist_text': band.therapist_text,
                           'content_version': band.content_version, 'content_format': band.content_format or 'book',
                           'talk_points': band.talk_points or False, 'definition': f.definition or False})
        return rows.sorted(lambda r: (r.factor_id.sequence, r.factor_id.id))

    # ------------------------------------------------------------------ per kind
    @api.model
    def ts_clinic(self):
        """{'battery', 'sections': [{'inst', 'results'}]} of BAT-INTAKE-1 (questionnaire parts only)."""
        b = self.env['ts.battery'].sudo().search([('code', '=', 'BAT-INTAKE-1'), ('state', '=', 'published')], limit=1)
        if not b:
            return None
        sections = []
        for line in b.ts_lines():
            inst = line.instrument_id.sudo()
            v = inst.current_version_id
            if not v or ('mode' in v._fields and v.mode not in (False, 'single')):
                continue
            try:
                sections.append({'inst': inst, 'results': self._results(v)})
            except Exception:       # noqa: BLE001 - a part that cannot be scored is left out of the sample
                continue
        return {'battery': b, 'sections': sections} if sections else None

    @api.model
    def ts_school(self):
        """(attempt, workspace) new() records for ts_talent's report_ctx (org view), or None."""
        from odoo.addons.ts_talent.models import engine_matrix as EM
        inst = self.env['ts.instrument'].sudo().search([('code', '=', 'TALENT-INV-15'), ('state', '=', 'published')], limit=1)
        v = inst.current_version_id if inst else None
        if not v:
            return None
        data = [{'label': label, 'answers': list(ans[:EM.ITEM_COUNT]), 'seconds': 120} for label, ans in TALENT_FIELDS]
        result = EM.score_matrix(data)
        profile = dict(result, interpretation=EM.interpret(result, gap=v.noise_gap))
        person = self.env['res.partner'].new({'name': SAMPLE_NAMES['school']})
        at = self.env['ts.attempt'].new({'instrument_id': inst.id, 'version_id': v.id, 'state': 'done', 'source': 'web',
                                         'released': True, 'profile_json': json.dumps(profile, ensure_ascii=False),
                                         'person_id': person.id, 'name': 'نمونه'})
        ws = self.env['ts.workspace'].new({'name': 'مدرسهٔ نمونه', 'purpose': 'education'})
        return at, ws

    @api.model
    def ts_hr(self):
        """{'res', 'r', 'occupation'} for ts_hire.candidate_fit: the job fit of a synthetic candidate for «کارشناس فروش»."""
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
        res = occ.ts_jobfit(facets=facets, abilities=dict(HR_ABILITIES))
        r = {'a': None, 'level': 'summary', 'res': res, 'band': res.get('band'), 'band_fa': J.BAND_FA[res.get('band')],
             'ws_band': res.get('ws') and res['ws'].get('band'), 'ab_band': res['ab'].get('band'),
             'explain': J.explain(res), 'flags': [], 'state': 'تکمیل‌شده', 'progress': None, 'decision': '', 'complete': True}
        return {'res': res, 'r': r, 'occupation': occ}

    @api.model
    def ts_kind_sample(self, kind):
        """{'kind', 'name', ...} with the kind's sample, or None when its instruments are not published."""
        kind = 'clinic' if kind == 'solo' else kind
        if kind == 'clinic':
            d = self.ts_clinic()
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
