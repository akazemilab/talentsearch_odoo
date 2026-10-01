"""Back-office views of tenants and data requests (S17, PLT-1, PLT-2, PLT-9).

Health columns count rows; they never show a client's name. Data requests get an overdue flag and state buttons for a platform
manager.
"""
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

OPEN = ('invited', 'opened', 'accepted', 'in_progress')


class TsWorkspaceHealth(models.Model):
    _inherit = 'ts.workspace'

    ts_member_count = fields.Integer('اعضا', compute='_compute_health')
    ts_client_count = fields.Integer('مراجعان', compute='_compute_health')
    ts_open_invites = fields.Integer('دعوت‌های باز', compute='_compute_health')
    ts_done_30d = fields.Integer('تکمیل در ۳۰ روز', compute='_compute_health')
    ts_last_activity = fields.Datetime('آخرین فعالیت', compute='_compute_health')
    ts_pending_days = fields.Integer('روز در انتظار', compute='_compute_health')

    @api.depends('state')
    def _compute_health(self):
        ids = self.ids
        zero = {i: 0 for i in ids}
        members, clients, opens, done, last = dict(zero), dict(zero), dict(zero), dict(zero), {}
        if ids:
            cr = self.env.cr
            since = fields.Datetime.now() - timedelta(days=30)
            cr.execute("SELECT workspace_id, COUNT(*) FROM ts_workspace_member WHERE active AND workspace_id IN %s GROUP BY 1", [tuple(ids)])
            members.update(dict(cr.fetchall()))
            cr.execute("SELECT workspace_id, COUNT(*), MAX(last_activity_at) FROM ts_panel_client WHERE state = 'active' "
                       "AND workspace_id IN %s GROUP BY 1", [tuple(ids)])
            for w, n, la in cr.fetchall():
                clients[w] = n
                last[w] = la
            cr.execute("SELECT workspace_id, COUNT(*) FROM ts_assignment WHERE state IN %s AND workspace_id IN %s GROUP BY 1",
                       [OPEN, tuple(ids)])
            opens.update(dict(cr.fetchall()))
            cr.execute("SELECT workspace_id, COUNT(*), MAX(submitted_at) FROM ts_attempt WHERE state = 'done' AND NOT voided "
                       "AND workspace_id IN %s AND submitted_at >= %s GROUP BY 1", [tuple(ids), since])
            for w, n, sa in cr.fetchall():
                done[w] = n
                if sa and (not last.get(w) or sa > last[w]):
                    last[w] = sa
        now = fields.Datetime.now()
        for ws in self:
            ws.ts_member_count = members.get(ws.id, 0)
            ws.ts_client_count = clients.get(ws.id, 0)
            ws.ts_open_invites = opens.get(ws.id, 0)
            ws.ts_done_30d = done.get(ws.id, 0)
            ws.ts_last_activity = last.get(ws.id) or False
            ws.ts_pending_days = (now - ws.create_date).days if ws.gated and ws.state in ('draft', 'pilot') and ws.create_date else 0


class TsDataRequestBackoffice(models.Model):
    _inherit = 'ts.data.request'

    overdue = fields.Boolean('عقب‌افتاده', compute='_compute_overdue')
    user_name = fields.Char('کاربر', related='user_id.name')

    @api.depends('due_on', 'state')
    def _compute_overdue(self):
        today = fields.Date.today()
        for r in self:
            r.overdue = bool(r.due_on and r.due_on < today and r.state in ('new', 'in_review'))

    def _ts_manager_only(self):
        if not self.env.user.has_group('ts_core.group_ts_manager'):
            raise UserError('فقط مدیر پلتفرم می‌تواند درخواست داده را رسیدگی کند.')

    def action_review(self):
        self._ts_manager_only()
        for r in self.filtered(lambda x: x.state == 'new'):
            r.sudo().write({'state': 'in_review', 'handled_by_id': self.env.uid})
            self.env['ts.audit.event'].sudo().log('data.request_handle', r, state='in_review')

    def action_decide(self, decision='done'):
        """Close a request. `done` for the normal outcome, otherwise the decision code (legal hold, not the owner, duplicate)."""
        self._ts_manager_only()
        if decision not in dict(self._fields['decision_code'].selection):
            raise UserError('تصمیم نامعتبر است.')
        for r in self.filtered(lambda x: x.state in ('new', 'in_review')):
            r.sudo().write({'state': 'done' if decision == 'done' else 'rejected', 'decision_code': decision,
                            'handled_by_id': self.env.uid})
            self.env['ts.audit.event'].sudo().log('data.request_handle', r, state=r.state, decision=decision)
            self.env['ts.notification']._notify(r.user_id, 'data_request_update', '/my/privacy')

    def action_done(self):
        self.action_decide('done')

    def action_reject_legal(self):
        self.action_decide('legal_hold')
