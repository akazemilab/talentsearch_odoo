import logging

from odoo import api, fields, models, _

from .phone_otp import iran_mobile

_logger = logging.getLogger(__name__)


class TsAssignment(models.Model):
    _inherit = 'ts.assignment'

    invitee_phone = fields.Char('موبایل شرکت‌کننده', copy=False)
    sms_consent = fields.Boolean('تأیید سازمان: شرکت‌کننده با دریافت پیامک موافق است', copy=False)
    sms_sent_at = fields.Datetime('زمان ارسال پیامک', readonly=True, copy=False)
    sms_error = fields.Char('خطای پیامک', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for a in recs:
            a._ts_send_invite_sms()
        return recs

    def _ts_send_invite_sms(self):
        self.ensure_one()
        company = (self.company_id or self.env.company).sudo()
        if not (self.invitee_phone and self.sms_consent and company.kv_enabled and company.ts_sms_invite):
            return False
        phone = iran_mobile(self.invitee_phone)
        if not phone:
            self.sms_error = 'شمارهٔ موبایل معتبر نیست'
            return False
        body = _('«%(org)s» شما را به یک سنجش در تلنت سرچ دعوت کرده است. پذیرش کاملاً اختیاری است:\n%(url)s',
                 org=self.workspace_id.name, url=self.invite_url())
        try:
            with self.env.cr.savepoint():
                sms = self.env['sms.sms'].sudo().with_company(company).create(
                    {'number': phone, 'body': body, 'sms_type': 'alert'})
                sms.send(unlink_sent=False, raise_exception=False)
                ok = sms.state in ('process', 'pending', 'sent')
                err = False if ok else dict(sms._fields['failure_type'].selection).get(sms.failure_type, 'خطا')
                sms.unlink()
        except Exception:
            _logger.exception('invitation SMS failed for assignment %s', self.id)
            ok, err = False, 'خطای سامانه'
        self.sudo().write({'sms_sent_at': fields.Datetime.now() if ok else False,
                           'sms_error': False if ok else str(err)[:200]})
        return ok
