from datetime import datetime, time, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.ts_org.models.panel import norm_phone

CHANNELS = [('link', 'پیوند'), ('sms', 'پیامک'), ('email', 'ایمیل'), ('open_link', 'پیوند باز'),
            ('self_share', 'اشتراک‌گذاری خود فرد'), ('import', 'واردشده')]


class TsAssignment(models.Model):
    _inherit = 'ts.assignment'

    client_id = fields.Many2one('ts.panel.client', 'مراجع', index=True, ondelete='restrict')
    state = fields.Selection(selection_add=[('opened', 'بازشده'), ('expired', 'منقضی')])
    channel = fields.Selection(CHANNELS, 'کانال', default='link')
    expires_at = fields.Datetime('انقضای دعوت', index=True)
    opened_at = fields.Datetime('نخستین بازشدن', readonly=True)
    expired = fields.Boolean('منقضی‌شده', readonly=True, index=True)
    remind_ok = fields.Boolean('تأیید یادآوری پیامکی', readonly=True, copy=False)
    # The client is the single place where responsibility is set (04_data_model.md 2.4). Writing this field
    # writes the client, so every older writer (old page, member leaving, accept) keeps working.
    responsible_id = fields.Many2one(related='client_id.responsible_id', readonly=False, string='کارشناس مسئول')

    @api.depends('withdrawn', 'declined', 'user_id', 'attempt_id.state', 'expired', 'opened_at')
    def _compute_state(self):
        super()._compute_state()
        for a in self:
            if a.state == 'invited':
                a.state = 'expired' if a.expired else ('opened' if a.opened_at else 'invited')

    @api.model
    def _ts_ttl_days(self):
        return self.env['ir.config_parameter'].sudo().get_int('ts_panel.invite_ttl_days', 30) or 30

    def _ts_default_expiry(self, deadline=None, base=None):
        """End of the deadline day when there is one, else base + invite_ttl_days (04_data_model.md 2.4)."""
        base = base or fields.Datetime.now()
        if deadline:
            return datetime.combine(fields.Date.to_date(deadline), time(23, 59, 59))
        return base + timedelta(days=self._ts_ttl_days())

    def invite_state(self):
        """The stored expiry replaces the read-time rule of ts_org (gap G9); everything else is unchanged."""
        self.ensure_one()
        res = super().invite_state()
        if res == 'expired' and self.expires_at and self.expires_at >= fields.Datetime.now() and not self.expired:
            return 'ok'     # extended: the old read-time rule (created + 30 d) no longer applies
        if res == 'ok' and (self.expired or (self.expires_at and self.expires_at < fields.Datetime.now())):
            return 'expired'
        return res

    @api.model_create_multi
    def create(self, vals_list):
        Client = self.env['ts.panel.client'].sudo()
        for vals in vals_list:
            if not vals.get('expires_at'):
                vals['expires_at'] = self._ts_default_expiry(vals.get('deadline'))
            if not vals.get('client_id') and vals.get('workspace_id'):
                vals['client_id'] = Client.ts_for_invitation(vals).id
            c = Client.browse(vals.get('client_id'))
            if c and c.state != 'active':
                raise UserError('این شرکت‌کننده بایگانی شده است؛ ابتدا او را بازیابی کنید.')
            if c and c.contact_locked:
                raise UserError('این فرد از دادهٔ تاریخی است و دعوت برای او فعلاً ممکن نیست.')
        recs = super().create(vals_list)
        for a in recs.filtered(lambda r: r.sms_sent_at and r.channel == 'link'):
            a.channel = 'sms'
        recs.client_id.ts_touch()
        return recs

    # ------------------------------------------------------------------ expiry (INV-3)
    def action_extend(self, days=None, by=None):
        """A new expiry for an invitation nobody accepted; clears `expired`."""
        days = self._ts_ttl_days() if days is None else int(days)
        if not 1 <= days <= 365:
            raise UserError('مدت تمدید باید بین ۱ تا ۳۶۵ روز باشد.')
        for a in self:
            if a.user_id or a.attempt_id or a.withdrawn or a.declined:
                raise UserError('فقط دعوتی که هنوز پذیرفته نشده تمدید می‌شود.')
            new = fields.Datetime.now() + timedelta(days=days)
            vals = {'expires_at': new, 'expired': False}
            if a.deadline and datetime.combine(a.deadline, time(23, 59, 59)) < new:
                vals['deadline'] = new.date()
            a.sudo().write(vals)
            self.env['ts.audit.event'].log('assignment.extend', a, workspace=a.workspace_id, days=days)

    def action_mark_opened(self):
        """First visit of the invitation link (the page of the participant)."""
        for a in self.sudo().filtered(lambda r: not r.opened_at and not r.user_id):
            a.opened_at = fields.Datetime.now()

    @api.model
    def ts_migrate_s6(self):
        """M3 rest (S6): expiry, channel and expired flag for invitations made before the stored expiry existed.
        Sends nothing; running it twice changes nothing. Returns counts."""
        cr = self.env.cr
        ttl = self._ts_ttl_days()
        cr.execute("""UPDATE ts_assignment SET expires_at = CASE WHEN deadline IS NOT NULL
                          THEN deadline + time '23:59:59' ELSE create_date + make_interval(days => %s) END
                        WHERE expires_at IS NULL""", [ttl])
        n_exp = cr.rowcount
        cr.execute("""UPDATE ts_assignment SET channel = CASE WHEN invited_by_id IS NOT NULL AND invited_by_id = user_id
                          THEN 'self_share' WHEN sms_sent_at IS NOT NULL THEN 'sms' ELSE 'link' END
                        WHERE channel IS NULL OR (channel = 'link' AND ((invited_by_id IS NOT NULL AND invited_by_id = user_id)
                          OR sms_sent_at IS NOT NULL))""")
        n_ch = cr.rowcount
        self.env.invalidate_all()
        late = self.with_context(active_test=False).sudo().search([
            ('expired', '=', False), ('user_id', '=', False), ('withdrawn', '=', False), ('declined', '=', False),
            ('attempt_id', '=', False), ('expires_at', '<', fields.Datetime.now())])
        late.write({'expired': True})
        return {'expires_at': n_exp, 'channel': n_ch, 'expired': len(late)}

    @api.model
    def _cron_expire_invitations(self):
        late = self.sudo().search([('expired', '=', False), ('user_id', '=', False), ('withdrawn', '=', False),
                                   ('declined', '=', False), ('attempt_id', '=', False),
                                   ('expires_at', '!=', False), ('expires_at', '<', fields.Datetime.now())])
        late.write({'expired': True})
        return len(late)

    def write(self, vals):
        res = super().write(vals)
        if vals.get('attempt_id'):
            for a in self.sudo():
                if a.client_id and not a.attempt_id.client_id:
                    a.attempt_id.client_id = a.client_id.id
        if vals.get('invitee_phone'):
            phone = norm_phone(vals['invitee_phone'])
            for c in self.sudo().client_id:
                if phone and not c.phone and not c.contact_locked:
                    c.phone = phone
        if set(vals) & {'user_id', 'attempt_id', 'withdrawn', 'declined', 'share_level'}:
            self.client_id.ts_touch()
        return res

    def action_accept(self, user, share):
        """Linking rule 1: the account is the key. Accepting links the account to the client."""
        self.ensure_one()
        client = self.client_id.sudo()
        if client.user_id and client.user_id != user:
            raise UserError('این دعوت قبلاً با حساب دیگری پذیرفته شده است.')
        attempt = super().action_accept(user, share)
        client = self.client_id.sudo()
        if client and not client.user_id:
            other = self.env['ts.panel.client'].sudo().search(
                [('workspace_id', '=', self.workspace_id.id), ('user_id', '=', user.id), ('id', '!=', client.id)], limit=1)
            if other:
                self.sudo().write({'client_id': other.id})
                if attempt.sudo().client_id == client:
                    attempt.sudo().client_id = other.id
                if not client.assignment_ids and not client.attempt_ids:
                    client.write({'state': 'archived', 'archived_on': fields.Datetime.now(), 'merged_into_id': other.id,
                                  'responsible_id': False})
                self.env['ts.audit.event'].log('client.auto_link', other, workspace=self.workspace_id)
                client = other
            else:
                client.user_id = user.id
        if client.responsible_id.user_id == user:
            client.responsible_id = False
        client.ts_touch()
        return attempt
