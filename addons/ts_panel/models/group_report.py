"""Group report with small-cell suppression (S13, REP-4, REP-5; 02_feature_catalog.md, 05_permissions_matrix.md section 5).

A group report counts people, never shows one person. Only results the member may open at summary or education level are
counted (the same `ts_result_level` as the single-result page). Every cell below `min_n` is hidden, 0 included; when exactly
one cell is hidden the next-smallest is hidden too, so a hidden value cannot be recovered from the total. An instrument with
fewer than `min_n` shared results shows only the threshold text.
"""
from datetime import timedelta

from odoo import api, fields, models

TALENT_CODE = 'TALENT-INV-15'
SCALES = ('ANA', 'EXP', 'ACA', 'NOV', 'DUT')
BANDS = ('low', 'mid', 'high')
BAND_KEY = {'medium': 'mid'}     # ts.attempt.result.band says 'medium'; the report's middle column is 'mid'
THRESHOLD_TEXT = 'برای گزارش گروهی دست‌کم %s نتیجهٔ به‌اشتراک‌گذاشته‌شده لازم است.'


def suppress(counts, k):
    """{key: n} -> {key: n or None}. Hides every cell below k; when exactly one is hidden hides the next-smallest too."""
    out = {key: (n if n >= k else None) for key, n in counts.items()}
    hidden = [key for key, v in out.items() if v is None]
    if len(hidden) == 1:
        rest = sorted((n, key) for key, n in counts.items() if out[key] is not None)
        if rest:
            out[rest[0][1]] = None
    return out


def _fa(n):
    return str(n).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))


class TsGroupReport(models.AbstractModel):
    _name = 'ts.group.report'
    _description = 'Talent Search group report builder'

    @api.model
    def min_n(self):
        return max(2, self.env['ir.config_parameter'].sudo().get_int('ts_panel.group_min_n', 5) or 5)

    @api.model
    def _attempts(self, member, params):
        """-> (shared attempts the member may open, all finished attempts in the same filter). One latest attempt per
        client and instrument; voided attempts are left out."""
        from ..controllers.clients import visible_domain          # lazy: the controllers import the models
        C = self.env['ts.panel.client'].sudo()
        dom = visible_domain(member) + [('state', '=', 'active')]
        if params.get('group_id'):
            dom.append(('group_ids', 'in', [int(params['group_id'])]))
        clients = C.search(dom)
        T = self.env['ts.attempt'].sudo()
        adom = [('workspace_id', '=', member.workspace_id.id), ('client_id', 'in', clients.ids), ('state', '=', 'done'),
                ('voided', '=', False)]
        if params.get('instrument_id'):
            adom.append(('instrument_id', '=', int(params['instrument_id'])))
        days = int(params.get('period') or 0)
        if days:
            adom.append(('submitted_at', '>=', fields.Datetime.now() - timedelta(days=days)))
        attempts = T.search(adom, order='submitted_at desc, id desc')
        if params.get('campaign_id'):
            ids = self.env['ts.assignment'].sudo().search(
                [('workspace_id', '=', member.workspace_id.id), ('campaign_id', '=', int(params['campaign_id']))]).attempt_id.ids
            attempts = attempts.filtered(lambda a: a.id in ids)
        seen, latest = set(), T
        for a in attempts:
            key = (a.client_id.id, a.instrument_id.id)
            if key not in seen:
                seen.add(key)
                latest |= a
        shared = latest.filtered(lambda a: a.ts_result_level(member) in ('summary', 'education'))
        return shared, latest

    @api.model
    def build(self, member, params):
        k = self.min_n()
        shared, latest = self._attempts(member, params)
        out = {'k': k, 'text': THRESHOLD_TEXT % _fa(k), 'instruments': [], 'imported': False}
        for inst in shared.instrument_id.sorted('name'):
            sh = shared.filtered(lambda a: a.instrument_id == inst)
            m = len(latest.filtered(lambda a: a.instrument_id == inst))
            row = {'id': inst.id, 'name': inst.ts_title(), 'n': len(sh), 'm': m, 'ok': len(sh) >= k,
                   'imported': any(a.source == 'import' for a in sh), 'factors': [], 'talent': None}
            out['imported'] = out['imported'] or row['imported']
            if row['ok']:
                if inst.code == TALENT_CODE:
                    row['talent'] = self._talent(sh.filtered(lambda a: a.ts_result_level(member) == 'education'), k)
                else:
                    row['factors'] = self._factors(sh, k)
            out['instruments'].append(row)
        return out

    @api.model
    def _factors(self, attempts, k):
        """One row per (instrument, factor code): results taken on different versions of an instrument (a new content
        version keeps the factor codes) are counted together. Name and order come from the instrument's current version
        when it still has the factor, else from the newest version seen."""
        res = self.env['ts.attempt.result'].sudo().search([('attempt_id', 'in', attempts.ids)])
        by, label = {}, {}
        for r in res:
            f = r.factor_id
            key = (r.attempt_id.instrument_id.id, f.code)
            by.setdefault(key, {b: 0 for b in BANDS})
            band = BAND_KEY.get(r.band, r.band)
            if band in BANDS:
                by[key][band] += 1
            cur = f.version_id == f.instrument_id.current_version_id
            old = label.get(key)
            if not old or (cur, f.version_id.id) > (old.version_id == old.instrument_id.current_version_id, old.version_id.id):
                label[key] = f
        return [{'name': label[key].name, 'total': sum(c.values()), 'cells': suppress(c, k)}
                for key, c in sorted(by.items(), key=lambda kv: (label[kv[0]].sequence, kv[0][1]))]

    @api.model
    def _talent(self, attempts, k):
        """Mean of each person's mean over fields per scale (only when n >= k), and how many people have each scale
        highest (suppressed). Field names never leave the person's own report."""
        if len(attempts) < k:
            return None
        sums = {s: 0.0 for s in SCALES}
        top = {s: 0 for s in SCALES}
        n = 0
        for a in attempts:
            fl = a.ts_profile().get('fields', [])
            if not fl:
                continue
            means = {s: sum(f.get('scales', {}).get(s, 0) for f in fl) / len(fl) for s in SCALES}
            for s in SCALES:
                sums[s] += means[s]
            top[max(SCALES, key=lambda s: (means[s], -SCALES.index(s)))] += 1
            n += 1
        if n < k:
            return None
        return {'n': n, 'means': {s: round(sums[s] / n, 1) for s in SCALES}, 'top': suppress(top, k)}
