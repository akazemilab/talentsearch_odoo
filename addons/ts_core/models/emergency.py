from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

EMERGENCY_HOURS = 24


class TsEmergencyAccess(models.Model):
    """Time-boxed, reasoned, audited access by a platform manager to the results of a CLINICAL panel, for
    the rare case that a participant at risk must be reached. The panel owners are told every time.
    Note: this is a procedure with a full trail; it does not remove the manager's technical read access."""
    _name = 'ts.emergency.access'
    _description = 'Talent Search emergency access'
    _order = 'id desc'

    workspace_id = fields.Many2one('ts.workspace', 'فضای کاری', required=True, ondelete='restrict',
                                   domain=[('purpose', '=', 'clinical')])
    user_id = fields.Many2one('res.users', 'مدیر پلتفرم', readonly=True, default=lambda s: s.env.user)
    reason = fields.Text('دلیل اضطراری', required=True)
    opened_at = fields.Datetime('شروع', readonly=True, default=fields.Datetime.now)
    expires_at = fields.Datetime('پایان', readonly=True)
    closed_at = fields.Datetime('بسته‌شده در', readonly=True)
    state = fields.Selection([('open', 'باز'), ('expired', 'منقضی'), ('closed', 'بسته')], compute='_compute_state')

    @api.model
    def _check_scope(self, vals):
        """Which panels this access may be opened on (hook: S14 widens it to every purpose)."""
        ws = self.env['ts.workspace'].browse(vals.get('workspace_id'))
        if ws.purpose != 'clinical':
            raise UserError('دسترسی اضطراری فقط برای پنل بالینی است.')

    @api.model
    def _hours(self, vals):
        """Length of the access in hours (hook: S14 lets a support access use another length)."""
        return EMERGENCY_HOURS

    @api.depends('expires_at', 'closed_at')
    def _compute_state(self):
        now = fields.Datetime.now()
        for r in self:
            r.state = 'closed' if r.closed_at else ('expired' if r.expires_at and r.expires_at < now else 'open')

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.user.has_group('ts_core.group_ts_manager'):
            raise UserError('فقط مدیر پلتفرم می‌تواند دسترسی اضطراری باز کند.')
        for vals in vals_list:
            self._check_scope(vals)
            if len((vals.get('reason') or '').strip()) < 15:
                raise UserError('دلیل اضطراری را دست‌کم در یک جمله کامل بنویسید.')
            vals.update({'user_id': self.env.uid, 'opened_at': fields.Datetime.now(),
                         'expires_at': fields.Datetime.now() + timedelta(hours=self._hours(vals))})
        recs = super().create(vals_list)
        for r in recs:
            ws = r.workspace_id
            hours = self._hours({'workspace_id': ws.id})
            self.env['ts.audit.event'].log('emergency.open', r, workspace=ws, hours=hours, reason_len=len(r.reason or ''))
            owners = ws.member_ids.filtered(lambda m: m.active and m.role == 'owner').user_id.partner_id
            ws.message_post(body='مدیر پلتفرم برای %d ساعت دسترسی اضطراری به نتایج این پنل باز کرد. دلیل: %s' % (
                hours, r.reason), partner_ids=owners.ids, message_type='notification',
                subtype_xmlid='mail.mt_comment')
        return recs

    def action_close(self):
        for r in self:
            if r.state == 'open':
                r.write({'closed_at': fields.Datetime.now()})
                self.env['ts.audit.event'].log('emergency.close', r, workspace=r.workspace_id)

    def action_view_results(self):
        """Opens the finished participants of the panel, only while the access is open; every open is logged."""
        self.ensure_one()
        if self.state != 'open' or self.user_id != self.env.user:
            raise UserError('این دسترسی اضطراری دیگر باز نیست.')
        self.env['ts.audit.event'].log('emergency.view', self, workspace=self.workspace_id)
        return {'type': 'ir.actions.act_window', 'name': 'نتایج پنل (دسترسی اضطراری)', 'res_model': 'ts.assignment',
                'view_mode': 'list,form', 'domain': [('workspace_id', '=', self.workspace_id.id), ('state', '=', 'done')]}
