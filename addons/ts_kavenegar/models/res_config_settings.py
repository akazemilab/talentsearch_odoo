from odoo import fields, models, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    kv_enabled = fields.Boolean(related='company_id.kv_enabled', readonly=False)
    kv_api_key = fields.Char(related='company_id.kv_api_key', readonly=False)
    kv_sender = fields.Char(related='company_id.kv_sender', readonly=False)
    kv_inbox_line = fields.Char(related='company_id.kv_inbox_line', readonly=False)
    kv_default_tag = fields.Char(related='company_id.kv_default_tag', readonly=False)
    kv_debug = fields.Boolean(related='company_id.kv_debug', readonly=False)
    kv_webhook_base = fields.Char(related='company_id.kv_webhook_base', readonly=False)
    kv_webhook_status_url = fields.Char(related='company_id.kv_webhook_status_url')
    kv_webhook_inbound_url = fields.Char(related='company_id.kv_webhook_inbound_url')
    kv_has_lookup = fields.Boolean(related='company_id.kv_has_lookup', readonly=False)
    kv_has_ip_whitelist = fields.Boolean(related='company_id.kv_has_ip_whitelist', readonly=False)
    kv_has_messenger = fields.Boolean(related='company_id.kv_has_messenger', readonly=False)
    kv_min_credit = fields.Integer(related='company_id.kv_min_credit', readonly=False)
    kv_alert_user_ids = fields.Many2many(related='company_id.kv_alert_user_ids', readonly=False)
    kv_credit = fields.Float(related='company_id.kv_credit')
    kv_expire = fields.Char(related='company_id.kv_expire')
    kv_account_type = fields.Char(related='company_id.kv_account_type')

    def _kv_notify(self, msg, kind='success'):
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': msg, 'type': kind, 'sticky': False}}

    def action_kv_generate_secret(self):
        self.execute()
        self.company_id.kv_generate_secret()
        return self._kv_notify(_('New webhook secret generated: update the two URLs in the Kavenegar panel.'))

    def action_kv_test(self):
        self.execute()
        c = self.company_id
        info = c.kv_sync_account()
        return self._kv_notify(_('Connected. Credit: %(c)s rial, expires %(e)s, account type %(t)s',
                                 c='{:,.0f}'.format(float(info.get('remaincredit') or 0)),
                                 e=info.get('expiredate'), t=info.get('type')))

    def action_kv_push_config(self):
        self.execute()
        self.company_id.kv_push_config()
        return self._kv_notify(_('Account configuration sent to Kavenegar.'))
