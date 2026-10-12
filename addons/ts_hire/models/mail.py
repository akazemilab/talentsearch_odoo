"""Email channel (owner decision 2026-10-12): invitations, reminders and the 'candidate finished' notice go out as native
mail.template emails through the outgoing server for sepehrtherapy.ir (Liara), sender ts_hire.email_from. Emails carry a
link only, never result content (same rule as SMS)."""
import logging
from datetime import datetime, time

from odoo import fields, models

from odoo.addons.ts_assessment.models.attempt import fa_digits, jalali

_logger = logging.getLogger(__name__)
DEFAULT_FROM = '"استعدادیاب" <no-reply@sepehrtherapy.ir>'


def _icp(env, key, default=''):
    return env['ir.config_parameter'].sudo().get_str(key, default)


class TsAssignmentMail(models.Model):
    _inherit = 'ts.assignment'

    # -------------------------------------------------- helpers used by the templates
    def ts_mail_org(self):
        self.ensure_one()
        ws = self.workspace_id.sudo()
        return ws.ts_public_name() if hasattr(ws, 'ts_public_name') else ws.name

    def ts_mail_minutes(self):
        self.ensure_one()
        n = self.battery_id.est_minutes if self.battery_id else self.instrument_id.duration_minutes
        return fa_digits(n or 0)

    def ts_mail_deadline(self):
        self.ensure_one()
        return jalali(datetime.combine(self.deadline, time(12, 0)), self.env, False) if self.deadline else ''

    def ts_mail_what(self):
        self.ensure_one()
        if self.position_id:
            return 'ارزیابی برای موقعیت «%s»' % self.position_id.name
        if self.battery_id:
            return 'مجموعهٔ «%s»' % self.battery_id.name
        return 'سنجهٔ «%s»' % (self.instrument_id.title or self.instrument_id.name)

    def ts_mail_staff_url(self):
        self.ensure_one()
        base = (self.env.ref('ts_website.website_ts').domain or '').rstrip('/')
        if self.position_id:
            return '%s/my/workspaces/%s/positions/%s/c/%s' % (base, self.workspace_id.id, self.position_id.id, self.id)
        return '%s/my/workspaces/%s' % (base, self.workspace_id.id)

    # -------------------------------------------------- sending
    def _ts_mail_server(self):
        """The outgoing server whose from_filter matches the sender's domain (Liara, sepehrtherapy.ir); never another."""
        sender = _icp(self.env, 'ts_hire.email_from', DEFAULT_FROM)
        domain = sender.split('@')[-1].strip(' >').lower()
        return self.env['ir.mail_server'].sudo().search([('from_filter', '=', domain)], limit=1)

    def _ts_email_enabled(self):
        return _icp(self.env, 'ts_hire.email_enabled', '1') == '1' and bool(self._ts_mail_server())

    def _ts_send_template(self, xmlid, email_to=None):
        self.ensure_one()
        tpl = self.env.ref(xmlid, raise_if_not_found=False)
        if not tpl or not self._ts_email_enabled():
            return False, 'ایمیل فعال نیست'
        to = email_to or (self.invitee_email or '').strip()
        if not to or '@' not in to:
            return False, 'نشانی ایمیل وارد نشده است'
        try:
            with self.env.cr.savepoint():
                tpl.sudo().send_mail(self.id, force_send=True, raise_exception=True, email_values={
                    'email_from': _icp(self.env, 'ts_hire.email_from', DEFAULT_FROM), 'email_to': to,
                    'mail_server_id': self._ts_mail_server().id, 'auto_delete': True})
            return True, ''
        except Exception as e:  # noqa: BLE001 - delivery problems are reported to the panel, never raised
            _logger.warning('email %s failed for assignment %s: %s', xmlid, self.id, type(e).__name__)
            return False, 'ارسال ایمیل ناموفق بود'

    def _ts_send_invite_email(self):
        self.ensure_one()
        ok, err = self._ts_send_template('ts_hire.mail_invite')
        self.sudo().write({'email_sent_at': fields.Datetime.now() if ok else False, 'email_error': err or False})
        if ok:
            self.env['ts.audit.event'].sudo().log('notify.email_invite', self, workspace=self.workspace_id)
        return ok

    def _ts_do_reminder(self):
        used = super()._ts_do_reminder()
        if self.invitee_email and not self.user_id:
            ok, _err = self._ts_send_template('ts_hire.mail_reminder')
            if ok:
                used = set(used) | {'email'}
                self.env['ts.audit.event'].sudo().log('notify.email_reminder', self, workspace=self.workspace_id)
        return used

    def _ts_mail_candidate_done(self):
        """Tell the inviting HR member (by email, if they have one) that a candidate finished; link only."""
        self.ensure_one()
        user = self.invited_by_id
        if user and user.email and '@' in user.email:
            self._ts_send_template('ts_hire.mail_candidate_done', email_to=user.email)
