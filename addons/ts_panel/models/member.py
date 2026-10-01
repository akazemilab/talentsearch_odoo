from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.ts_core.models.workspace import ROLES_BY_PURPOSE


class TsMemberInvite(models.Model):
    _inherit = 'ts.member.invite'

    def ts_resend(self, by_member):
        """MEM-3: revoke the old link (it stops working at once) and issue a new 7-day link for the same person."""
        self.ensure_one()
        if self.workspace_id != by_member.workspace_id or not by_member.has_perm('members:invite'):
            raise UserError('دسترسی ندارید.')
        if self.state != 'pending':
            raise UserError('فقط دعوتِ در انتظار دوباره فرستاده می‌شود.')
        if self.role == 'owner' and not by_member.has_perm('members:add_owner'):
            raise UserError('فقط مالک می‌تواند مالک دیگری اضافه کند.')
        old = self
        old.action_revoke()
        new = self.ts_create(by_member, old.role, phone_raw=old.phone, email_raw=old.email)
        self.env['ts.audit.event'].sudo().log('member.invite_resend', new, workspace=new.workspace_id, role=new.role,
                                              by=by_member.user_id.id)
        return new


class TsWorkspaceMember(models.Model):
    _inherit = 'ts.workspace.member'

    def ts_client_count(self):
        """Participants (invitations and imported results) this member is responsible for."""
        self.ensure_one()
        return (self.env['ts.assignment'].sudo().search_count([('responsible_id', '=', self.id)])
                + self.env['ts.attempt'].sudo().search_count([('responsible_id', '=', self.id)]))

    def ts_last_activity(self):
        self.ensure_one()
        ev = self.env['ts.audit.event'].sudo().search(
            [('workspace_id', '=', self.workspace_id.id), ('actor_id', '=', self.user_id.id)], limit=1)
        return ev.create_date if ev else False

    def ts_state_key(self):
        """active | awaiting | inactive (the vocabulary of 08_design_system.md section 3)."""
        self.ensure_one()
        if not self.active:
            return 'inactive'
        return 'awaiting' if self._ts_unverified_pro() else 'active'

    # ------------------------------------------------------------------ changes by an owner
    def _ts_check_manager(self, by, perm='members:manage'):
        self.ensure_one()
        if by.workspace_id != self.workspace_id or not by.has_perm(perm):
            raise UserError('دسترسی ندارید.')

    def ts_change_role(self, by, new_role):
        """MEM-4. The write() of ts_core guards the last owner; ts_org releases clients the new role cannot hold."""
        self._ts_check_manager(by)
        if not self.active:
            raise UserError('عضو غیرفعال را ابتدا فعال کنید.')
        if new_role not in ROLES_BY_PURPOSE.get(self.workspace_id.purpose, set()):
            raise UserError('این نقش برای این نوع پنل مجاز نیست.')
        if new_role == 'owner':
            by._ts_check_manager(by, 'members:add_owner')
        if new_role == self.role:
            return False
        vals = {'role': new_role}
        if self.role == 'owner':
            vals['owner_practices'] = False
        self.sudo().write(vals)
        return True

    def ts_deactivate(self, by):
        """MEM-5. Returns the number of participants that went back to the unassigned queue."""
        self._ts_check_manager(by)
        if not self.active:
            raise UserError('این عضو از پیش غیرفعال است.')
        n = self.ts_client_count()
        self.sudo().write({'active': False})
        return n

    def ts_reactivate(self, by):
        self._ts_check_manager(by)
        if self.active:
            raise UserError('این عضو از پیش فعال است.')
        self.sudo().write({'active': True})

    def ts_set_practising(self, by, flag, license_number=None):
        """MEM-7: an owner who also sees clients. In a clinical panel this needs the licence number and starts
        verification (the verification state is computed from the role and this flag)."""
        self.ensure_one()
        if by != self or self.role != 'owner':
            raise UserError('فقط مالک می‌تواند این گزینه را برای خودش تغییر دهد.')
        vals = {'owner_practices': bool(flag)}
        if flag and self.workspace_id.purpose == 'clinical':
            lic = (license_number or self.license_number or '').strip()[:60]
            if not lic:
                raise UserError('برای دیدن گزارش بالینی، شمارهٔ پروانه یا نظام حرفه‌ای لازم است.')
            vals['license_number'] = lic
        self.sudo().write(vals)
        self.env['ts.audit.event'].sudo().log('member.practice', self, workspace=self.workspace_id,
                                              practising=bool(flag))

    # ------------------------------------------------------------------ responsibility lives on the client
    @api.model
    def ts_default_responsible(self, workspace_id, user_id):
        """The assignment no longer takes a default of its own: the CLIENT does (see ts_panel_default_responsible)."""
        return self.browse()

    @api.model
    def ts_panel_default_responsible(self, workspace_id, user_id):
        return super().ts_default_responsible(workspace_id, user_id)

    def _ts_release_clients(self):
        super()._ts_release_clients()
        self.env['ts.panel.client'].sudo().search([('responsible_id', 'in', self.ids)]).write({'responsible_id': False})
