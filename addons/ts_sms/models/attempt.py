import logging

from odoo import models, _

_logger = logging.getLogger(__name__)


class TsAttempt(models.Model):
    _inherit = 'ts.attempt'

    def action_submit(self, submission_key=None):
        was_done = self.state == 'done'
        res = super().action_submit(submission_key=submission_key)
        if res and not was_done and self.state == 'done':
            self._ts_notify_result_ready()
        return res

    def _ts_notify_result_ready(self):
        """SMS with NO result content: only tells the person a result exists."""
        self.ensure_one()
        company = self.env.company.sudo()
        partner = self.sudo().partner_id
        if not (company.kv_enabled and company.ts_sms_result and partner.ts_phone and partner.ts_sms_results):
            return False
        ws = self.sudo().workspace_id if 'workspace_id' in self._fields else False
        if ws and ws.state != 'active':
            return False          # onb1 risk review: a suspended or closed panel sends nothing (the result stays on «/my»)
        body = self._ts_result_sms_body()
        try:
            with self.env.cr.savepoint():
                sms = self.env['sms.sms'].sudo().with_company(company).create(
                    {'number': partner.ts_phone, 'body': body, 'sms_type': 'alert', 'partner_id': partner.id})
                sms.send(unlink_sent=True, raise_exception=False)
        except Exception:
            _logger.exception('result SMS failed for attempt %s', self.id)
            return False
        return True

    def _ts_result_sms_body(self):
        """Text of the result-ready SMS (a link, never result content). ts_brand renders it from an sms.template."""
        self.ensure_one()
        base = (self.env.ref('ts_website.website_ts').domain or '').rstrip('/')
        return _('نتیجهٔ سنجهٔ شما در استعدادیاب آماده است. برای دیدن آن وارد حساب خود شوید:\n%s/my/assessments', base)
