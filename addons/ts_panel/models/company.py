from odoo import fields, models


class ResCompanyNotify(models.Model):
    _inherit = 'res.company'

    ts_sms_reminder = fields.Boolean('Talent Search: reminder SMS (one per invitation)', default=False)
    ts_sms_staff = fields.Boolean('Talent Search: SMS to panel staff (result ready, panel approved/rejected/suspended)', default=False)


class ResConfigSettingsNotify(models.TransientModel):
    _inherit = 'res.config.settings'

    ts_sms_reminder = fields.Boolean(related='company_id.ts_sms_reminder', readonly=False)
    ts_sms_staff = fields.Boolean(related='company_id.ts_sms_staff', readonly=False)
