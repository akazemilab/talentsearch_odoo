import calendar
from collections import defaultdict

from odoo import fields, models

from .mail_notification import KV_FAILURES


class SmsSms(models.Model):
    _inherit = 'sms.sms'

    failure_type = fields.Selection(selection_add=KV_FAILURES)
    kv_sender = fields.Char('Kavenegar sender line')
    kv_date = fields.Datetime('Send at (Kavenegar schedule)', help='Kavenegar delivers it at that time (can be cancelled).')
    kv_tag = fields.Char('Tag')
    kv_hide = fields.Boolean('Hide number in the panel')
    kv_policy = fields.Char('Policy')
    kv_type = fields.Selection([('0', 'Flash (0)'), ('1', 'Mobile memory (1)'), ('2', 'Sim (2)'), ('3', 'App (3)')],
                               string='Display type', help='Only for 3000-lines.')
    kv_media_id = fields.Many2one('kavenegar.media', 'Media', ondelete='set null')
    kv_secret = fields.Boolean('Secret text', help='OTP-like text: the body is masked in the Kavenegar log.')

    def _split_by_api(self):
        by_company = defaultdict(lambda: self.env['sms.sms'])
        rest = self.browse()
        for sms in self:
            by_company[sms._get_sms_company()] += sms
        for company, recs in by_company.items():
            if company.kv_enabled:
                api = company._get_sms_api_class()(self.env)
                api._set_company(company)
                yield api, recs
            else:
                rest += recs
        if rest:
            yield from super(SmsSms, rest)._split_by_api()

    def _get_send_batch_size(self):
        if self.env.company.sudo().kv_enabled:
            return 200
        return super()._get_send_batch_size()

    def _kv_extras(self):
        self.ensure_one()
        date = calendar.timegm(self.kv_date.utctimetuple()) if self.kv_date else None
        return {
            'sender': self.kv_sender or None, 'date': date, 'tag': self.kv_tag or None,
            'hide': self.kv_hide, 'policy': self.kv_policy or None,
            'type': int(self.kv_type) if self.kv_type else None,
            'mediaid': self.kv_media_id.remote_id or None,
            'secret': self.kv_secret,
        }

    def _send_with_api(self, sms_api, unlink_sent=True, raise_exception=False):
        if hasattr(sms_api, '_extras'):
            sms_api._extras = {s.uuid: s._kv_extras() for s in self}
        return super()._send_with_api(sms_api, unlink_sent=unlink_sent, raise_exception=raise_exception)

    def _handle_call_result_hook(self, results):
        logs = [dict(r['kv']) for r in results if r.get('kv')]
        if logs:
            self.env['kavenegar.message'].sudo()._kv_log_sent(logs)
        return super()._handle_call_result_hook(results)
