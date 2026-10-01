"""Panel lifecycle (S18, ORG-7, ORG-8, PRV-4): ownership transfer, closing a panel, anonymising a client.

All three leave audit events with ids and counts only.
"""
from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.ts_core.models.workspace import ROLES_BY_PURPOSE

CLOSE_DAYS = 90
ANON_NAME = 'مراجع ناشناس'


class TsWorkspaceLifecycle(models.Model):
    _inherit = 'ts.workspace'

    closed_on = fields.Datetime('زمان بسته‌شدن', readonly=True, copy=False)

    def ts_transfer(self, by, new_owner, stay='admin'):
        """ORG-7: `new_owner` (an active member) becomes owner; the old owner stays owner or becomes admin."""
        self.ensure_one()
        if by.workspace_id != self or by.role != 'owner' or not by.active or not by.has_perm('panel:transfer'):
            raise UserError('فقط مالک پنل می‌تواند مالکیت را منتقل کند.')
        if new_owner.workspace_id != self or not new_owner.active or new_owner == by:
            raise UserError('عضو انتخاب‌شده معتبر نیست.')
        if stay not in ('owner', 'admin'):
            raise UserError('نقش بعدی مالک فعلی معتبر نیست.')
        if stay == 'admin' and 'admin' not in ROLES_BY_PURPOSE.get(self.purpose, set()):
            stay = 'owner'
        if new_owner.role == 'owner':
            raise UserError('این عضو از پیش مالک است.')
        new_owner.sudo().write({'role': 'owner'})
        if stay != 'owner':
            by.sudo().write({'role': stay, 'owner_practices': False})
        self.env['ts.audit.event'].sudo().log('panel.transfer', self, workspace=self, member=by, to=new_owner.id, stay=stay)
        N = self.env['ts.notification']
        for m in (new_owner, by):
            N._notify(m.user_id, 'panel_transferred', '/my/workspaces/%s' % self.id, self)
        return True

    def ts_close(self, by):
        """ORG-8: no new invitations, 90 days for the owner to export, then the clients are anonymised."""
        self.ensure_one()
        if by.workspace_id != self or by.role != 'owner' or not by.active or not by.has_perm('panel:close'):
            raise UserError('فقط مالک پنل می‌تواند آن را ببندد.')
        if self.state not in ('pilot', 'active', 'suspended'):
            raise UserError('این پنل را نمی‌توان بست.')
        self.sudo().write({'state': 'closed', 'closed_on': fields.Datetime.now()})
        self.env['ts.audit.event'].sudo().log('panel.close', self, workspace=self, member=by)
        N = self.env['ts.notification']
        for m in self.sudo().member_ids.filtered(lambda m: m.active and m.role == 'owner'):
            N._notify(m.user_id, 'panel_closed', '/my/workspaces/%s' % self.id, self)
        return True


class TsPanelClientLifecycle(models.Model):
    _inherit = 'ts.panel.client'

    def ts_anonymise(self):
        """Empty the contact and guardian fields; the row, the counts and the person's own results stay."""
        n = 0
        for c in self.sudo():
            if c.anonymised_on:
                continue
            c.write({'name': ANON_NAME, 'code': False, 'phone': False, 'email': False, 'guardian_name': False,
                     'guardian_phone': False, 'guardian_relation': False, 'user_id': False, 'partner_id': False,
                     'state': 'archived', 'anonymised_on': fields.Datetime.now()})
            for a in c.assignment_ids:
                a.write({'invitee_name': ANON_NAME, 'invitee_email': False, 'invitee_phone': False})
            n += 1
        return n


def closed_due(env, days=CLOSE_DAYS):
    """Closed panels past their export window that still hold clients with contact data."""
    since = fields.Datetime.now() - timedelta(days=days)
    return env['ts.workspace'].sudo().search([('state', '=', 'closed'), ('closed_on', '<=', since)])
