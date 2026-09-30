from odoo import models


class TsAttempt(models.Model):
    _inherit = 'ts.attempt'

    def ts_org_assignment(self):
        """The workspace invitation behind this attempt (owner-only use in the report)."""
        self.ensure_one()
        return self.env['ts.assignment'].sudo().search(
            [('attempt_id', '=', self.id), ('user_id', '=', self.user_id.id)], limit=1)

    def ts_org_visible_to(self, member):
        """Education workspaces: may this member (owner/counselor of the institute)
        open the participant report of this attempt? Answers are never included.

        Imported historical results of the workspace are visible to its usable
        members; web attempts only through a released assignment with sharing on."""
        self.ensure_one()
        ws = member.workspace_id
        if ws.purpose != 'education' or not member.can_act() or self.workspace_id != ws:
            return False
        if self.state != 'done':
            return False
        if self.source == 'import':
            return True
        a = self.env['ts.assignment'].sudo().search(
            [('attempt_id', '=', self.id), ('workspace_id', '=', ws.id)], limit=1)
        return bool(a) and a.visible_results(member)[0] == 'education'
