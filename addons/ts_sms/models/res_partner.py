from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    ts_phone = fields.Char('Talent Search verified mobile', copy=False, readonly=True)
    ts_phone_verified_at = fields.Datetime(copy=False, readonly=True)
    ts_sms_results = fields.Boolean('Notify by SMS when a result is ready', copy=False)
