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
        """active | inactive (08_design_system.md section 3; «awaiting» verification is gone since onb1)."""
        self.ensure_one()
        return 'active' if self.active else 'inactive'

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
        """MEM-7: an owner who also sees clients. In a counseling center this opens the full reports, so (onb1 risk
        review) it needs a licence number, self-declared: the badge stays «ثبت‌شده، هنوز تأیید نشده» until the super
        admin checks it, and the panel shows up in the back-office list «مالک مشاور شد (بررسی پروانه)»."""
        self.ensure_one()
        if by != self or self.role != 'owner':
            raise UserError('فقط مالک می‌تواند این گزینه را برای خودش تغییر دهد.')
        clinical = self.workspace_id.purpose == 'clinical'
        vals = {'owner_practices': bool(flag)}
        if license_number is not None and clinical:
            vals['license_number'] = (license_number or '').strip()[:60] or False
        lic = vals.get('license_number', self.license_number) if clinical else False
        if flag and clinical and not lic:
            raise UserError('برای مشاوره در این مرکز، شمارهٔ پروانه یا نظام روان‌شناسی و مشاوره‌تان را بنویسید. '
                            'کار شما منتظر بررسی آن نمی‌ماند؛ نشان «پروانهٔ تأییدشده» پس از بررسی تیم استعدادیاب می‌آید.')
        started = bool(flag) and not self.owner_practices
        if started and clinical:
            vals['practising_since'] = fields.Datetime.now()
        elif not flag:
            vals['practising_since'] = False
        self.sudo().write(vals)
        self.env['ts.audit.event'].sudo().log('member.practice', self, workspace=self.workspace_id,
                                              practising=bool(flag), licence_self_declared=bool(lic))
        if started and clinical:
            self.workspace_id.sudo().message_post(
                body='مالک این مرکز اعلام کرد خودش هم مشاوره می‌کند و گزارش کامل مراجعان را می‌بیند (شمارهٔ پروانه هنوز بررسی نشده است).',
                message_type='comment', subtype_xmlid='mail.mt_note')

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
