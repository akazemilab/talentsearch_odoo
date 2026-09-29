from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ts_sms_invite = fields.Boolean(related='company_id.ts_sms_invite', readonly=False)
    ts_sms_result = fields.Boolean(related='company_id.ts_sms_result', readonly=False)
    ts_sms_otp = fields.Boolean(related='company_id.ts_sms_otp', readonly=False)
    ts_sms_otp_template_id = fields.Many2one(related='company_id.ts_sms_otp_template_id', readonly=False)
