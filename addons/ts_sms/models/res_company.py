from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    ts_sms_invite = fields.Boolean('Talent Search: invitation SMS', default=True)
    ts_sms_result = fields.Boolean('Talent Search: result-ready SMS', default=True)
    ts_sms_otp = fields.Boolean('Talent Search: mobile verification', default=True)
    ts_sms_otp_template_id = fields.Many2one(
        'kavenegar.template', 'OTP template (Verify Lookup)',
        domain="[('approval', '=', 'Approved')]",
        help='Approved Kavenegar template whose text contains %token. Without it a plain SMS is used.')
