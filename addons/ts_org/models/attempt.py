from odoo import models


class TsAttempt(models.Model):
    _inherit = 'ts.attempt'

    def ts_org_assignment(self):
        """The workspace invitation behind this attempt (owner-only use in the report)."""
        self.ensure_one()
        return self.env['ts.assignment'].sudo().search(
            [('attempt_id', '=', self.id), ('user_id', '=', self.user_id.id)], limit=1)
