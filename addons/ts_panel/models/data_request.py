"""A person's requests about their own data (S15, ACC-5, ACC-6; 04_data_model.md 3.9).

`export`: a background job (kind `data_export`) builds a ZIP with one JSON and one CSV of the person's own profile, attempts,
results at participant level, shares and consents. No item keys, no answers, no other person's data. The link lives 24 h.
`erase`: only recorded here with a due date 30 days ahead; a platform manager executes it (the erase workflow ships in S18).
"""
import csv
import io
import json
import zipfile
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

KINDS = [('export', 'دریافت نسخهٔ داده‌ها'), ('erase', 'حذف داده‌ها'), ('correct', 'اصلاح داده‌ها')]
STATES = [('new', 'ثبت شد'), ('in_review', 'در حال بررسی'), ('done', 'انجام شد'), ('rejected', 'رد شد')]
DECISIONS = [('done', 'انجام شد'), ('legal_hold', 'نگه‌داری الزام قانونی'), ('not_owner', 'درخواست‌دهنده مالک داده نیست'),
             ('duplicate', 'درخواست تکراری')]
DUE_DAYS = 30


class TsDataRequest(models.Model):
    _name = 'ts.data.request'
    _description = 'Talent Search data request'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='restrict')
    kind = fields.Selection(KINDS, required=True, index=True)
    state = fields.Selection(STATES, default='new', required=True, index=True)
    due_on = fields.Date()
    handled_by_id = fields.Many2one('res.users', ondelete='set null')
    decision_code = fields.Selection(DECISIONS)
    job_id = fields.Many2one('ts.job', ondelete='set null')

    # ------------------------------------------------------------------ creating
    @api.model
    def ts_open(self, user, kind):
        """The person asks for an export or an erase. One open request per kind at a time."""
        if kind not in ('export', 'erase'):
            raise UserError('این نوع درخواست ممکن نیست.')
        S = self.sudo()
        open_ = S.search([('user_id', '=', user.id), ('kind', '=', kind), ('state', 'in', ('new', 'in_review'))], limit=1)
        if open_ and kind == 'erase':
            raise UserError('درخواست حذف شما پیش‌تر ثبت شده و در حال بررسی است.')
        req = S.create({'user_id': user.id, 'kind': kind, 'due_on': fields.Date.today() + timedelta(days=DUE_DAYS)})
        if kind == 'export':
            job = self.env['ts.job'].sudo().create({'user_id': user.id, 'kind': 'data_export', 'state': 'queued'})
            req.job_id = job.id
            job.ts_run(commit=False)
            req.state = 'done' if job.state == 'done' else 'in_review'
            if job.state == 'done':
                req.decision_code = 'done'
        self.env['ts.audit.event'].sudo().log('data.request', req, kind=kind)
        return req

    # ------------------------------------------------------------------ the export content
    @api.model
    def ts_payload(self, user):
        """Everything the person may take away; ids of their own rows only, no answers, no item keys."""
        env = self.env
        U = user.sudo()
        phone = U.partner_id.ts_phone if 'ts_phone' in U.partner_id._fields else False
        attempts, results = [], []
        for at in env['ts.attempt'].sudo().search([('user_id', '=', U.id)], order='id'):
            attempts.append({'id': at.id, 'instrument': at.instrument_id.code, 'title': at.instrument_id.title, 'state': at.state,
                             'started': str(at.started_at or ''), 'submitted': str(at.submitted_at or ''),
                             'panel_attempt': bool(at.workspace_id)})
            if at.state == 'done' and at.released:
                if at.ts_is_matrix():
                    results.append({'attempt': at.id, 'profile': at.ts_profile()})
                else:
                    for r in at.result_rows():
                        results.append({'attempt': at.id, 'factor': r.factor_id.name, 'score': round(r.score, 2), 'band': r.band or ''})
        shares = []
        for a in env['ts.assignment'].sudo().search([('user_id', '=', U.id), ('attempt_id', '!=', False)], order='id'):
            shares.append({'attempt': a.attempt_id.id, 'panel': a.workspace_id.name, 'level': a.share_level,
                           'by_you': a.invited_by_id == U})
        consents = [{'kind': c.kind, 'version': c.version or '', 'at': str(c.at), 'level': c.level or '', 'attempt': c.attempt_id.id}
                    for c in env['ts.consent.record'].sudo().search([('user_id', '=', U.id)], order='id')]
        return {'profile': {'name': U.name, 'login': U.login, 'verified_mobile': phone or ''}, 'attempts': attempts,
                'results': results, 'shares': shares, 'consents': consents, 'generated': str(fields.Datetime.now())}

    @api.model
    def ts_zip(self, payload):
        """-> bytes of a ZIP with my-data.json and my-data.csv (one table: section, key, value)."""
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(['section', 'row', 'field', 'value'])
        for section, val in payload.items():
            rows = val if isinstance(val, list) else [val]
            for i, row in enumerate(rows, 1):
                if isinstance(row, dict):
                    for k, v in row.items():
                        w.writerow([section, i, k, json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v])
                else:
                    w.writerow([section, i, '', row])
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('my-data.json', json.dumps(payload, ensure_ascii=False, indent=1))
            z.writestr('my-data.csv', '﻿' + buf.getvalue())
        return out.getvalue()
