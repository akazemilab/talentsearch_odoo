from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _ts_verified_phones(self):
        """Mobile numbers this user has proven; ts_sms extends it."""
        return []
