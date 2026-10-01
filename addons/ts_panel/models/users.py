from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def ts_panel_home(self):
        """Target of the role-aware header link «پنل من»: the panel itself when the person belongs to exactly one,
        the list of panels when to several, False for everybody else."""
        self.ensure_one()
        if self._is_public():
            return False
        ms = self.env['ts.workspace.member'].sudo().search([('user_id', '=', self.id), ('active', '=', True)])
        if not ms:
            return False
        if len(ms) == 1:
            return '/my/workspaces/%s/home' % ms.workspace_id.id
        return '/my/workspaces'
