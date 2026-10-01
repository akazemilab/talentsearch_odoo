"""Support access = the emergency access of ts_core, generalised (S14, SUP-1; 04_data_model.md 3.10).

`kind` is `emergency` (clinical panels only, 24 h, reason) or `support` (any panel, 8 h, reason and a ticket reference). The owners
of the panel are notified every time and see every access on the panel's audit page.
"""
from odoo import api, fields, models
from odoo.exceptions import UserError

SUPPORT_HOURS = 8


class TsSupportAccess(models.Model):
    _inherit = 'ts.emergency.access'

    kind = fields.Selection([('emergency', 'اضطراری'), ('support', 'پشتیبانی')], 'نوع', default='emergency', required=True)
    ticket_ref = fields.Char('شمارهٔ تیکت', size=60)

    @api.model
    def _check_scope(self, vals):
        if (vals.get('kind') or 'emergency') != 'support':
            return super()._check_scope(vals)
        if not self.env['ts.workspace'].browse(vals.get('workspace_id')).exists():
            raise UserError('پنل پیدا نشد.')
        if len((vals.get('ticket_ref') or '').strip()) < 3:
            raise UserError('برای دسترسی پشتیبانی شمارهٔ تیکت لازم است.')

    @api.model
    def _hours(self, vals):
        return SUPPORT_HOURS if vals.get('kind') == 'support' else super()._hours(vals)

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        N = self.env['ts.notification']
        for r in recs:
            ws = r.workspace_id
            if r.kind == 'support':
                self.env['ts.audit.event'].log('support.open', r, workspace=ws, hours=SUPPORT_HOURS)
            for m in ws.member_ids.filtered(lambda m: m.active and m.role == 'owner'):
                N._notify(m.user_id, 'support_access_opened', '/my/workspaces/%d/audit' % ws.id, ws)
        return recs
