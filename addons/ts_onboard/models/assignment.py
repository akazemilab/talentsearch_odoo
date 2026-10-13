"""O2: how an invitation reached the person, and the browser it is bound to.

* `delivered_via`: sms / email / manual (a copied link, a QR code, an open link, a panel that typed no number). Set by the
  existing SMS and e-mail send paths when they report success (invitation or reminder); the number or address the link
  went to is kept (`delivered_phone`, `delivered_email`), because the link in that message proves that number or address.
* `device_hash`: sha256 of the browser token of the first accept (cookie ts_dev, HttpOnly, SameSite=Lax). The raw token
  is never stored.
* The welcome screen's POST is the consent: `welcome_version` (the consent text version) and `welcome_at`.
"""
from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.ts_sms.models.phone_otp import iran_mobile

DELIVERY = [('manual', 'پیوند یا کد QR'), ('sms', 'پیامک'), ('email', 'ایمیل')]


class TsAssignmentDelivery(models.Model):
    _inherit = 'ts.assignment'

    delivered_via = fields.Selection(DELIVERY, 'راه رسیدن دعوت', default='manual', required=True, readonly=True, copy=False)
    delivered_phone = fields.Char('شماره‌ای که پیامک دعوت به آن رسید', readonly=True, copy=False,
                                  groups='ts_core.group_ts_manager')
    delivered_email = fields.Char('نشانی‌ای که ایمیل دعوت به آن رسید', readonly=True, copy=False,
                                  groups='ts_core.group_ts_manager')
    device_hash = fields.Char(readonly=True, copy=False, index=True, groups='base.group_system')
    welcome_version = fields.Char('نسخهٔ متن رضایت (صفحهٔ خوش‌آمد)', readonly=True, copy=False)
    welcome_at = fields.Datetime('زمان رضایت (صفحهٔ خوش‌آمد)', readonly=True, copy=False)

    # ------------------------------------------------------------------ the send paths report delivery
    def _ts_mark_delivered(self, via, phone=None, email=None):
        for a in self.sudo():
            if via == 'sms' and phone:
                a.write({'delivered_via': 'sms', 'delivered_phone': phone})
            elif via == 'email' and email and '@' in email:
                vals = {'delivered_email': email.strip().lower()}
                if a.delivered_via != 'sms':
                    vals['delivered_via'] = 'email'
                a.write(vals)

    def _ts_send_invite_sms(self):
        ok = super()._ts_send_invite_sms()
        if ok:
            self._ts_mark_delivered('sms', phone=iran_mobile(self.invitee_phone or ''))
        return ok

    def _ts_send_invite_email(self):
        ok = super()._ts_send_invite_email()
        if ok:
            self._ts_mark_delivered('email', email=self.invitee_email)
        return ok

    def _ts_do_reminder(self):
        used = super()._ts_do_reminder()
        if 'sms' in used:
            self._ts_mark_delivered('sms', phone=iran_mobile(self.invitee_phone or ''))
        if 'email' in used:
            self._ts_mark_delivered('email', email=self.invitee_email)
        return used

    def action_decline(self, user):
        """«نمی‌خواهم شرکت کنم» from a visitor who is not signed in (the link is the key of this one invitation): the
        invitation is declined without tying it to any account; the panel's hold is released as for any decline."""
        if user and user._is_public():
            for a in self.sudo():
                if a.user_id or a.attempt_id:
                    raise UserError('این دعوت دیگر قابل رد نیست.')
                a.write({'declined': True})
                self.env['ts.audit.event'].sudo().log('assignment.decline', a, workspace=a.workspace_id, signed_in=False)
            if hasattr(self, '_ts_billing_release'):
                self._ts_billing_release('decline')
            return True
        return super().action_decline(user)

    # ------------------------------------------------------------------ who the invitation is for
    def ts_proof(self):
        """(via, value) that the link itself proves: ('sms', number), ('email', address) or (None, None)."""
        self.ensure_one()
        s = self.sudo()
        if s.delivered_via == 'sms' and s.delivered_phone:
            return 'sms', s.delivered_phone
        if s.delivered_via == 'email' and s.delivered_email:
            return 'email', s.delivered_email
        return None, None

    def ts_invite_phone(self):
        """The number of this invitation: the one the SMS reached, else the number the panel wrote (may be empty)."""
        self.ensure_one()
        s = self.sudo()
        return s.delivered_phone or iran_mobile(s.invitee_phone or '') or ''

    def ts_contact_matches(self, user):
        """True / False when the invitation names a number (or a proven e-mail address) and `user` holds it or not;
        None when the invitation names neither (a copied link or QR code without a number): then nothing is checked."""
        self.ensure_one()
        via, value = self.ts_proof()
        phone = self.ts_invite_phone()
        if phone and via != 'email':
            phones = set(user.sudo()._ts_verified_phones() or []) | {user.sudo().login}
            return phone in phones
        if via == 'email':
            u = user.sudo()
            return value in {(u.login or '').strip().lower(), (u.email or '').strip().lower()}
        return None
