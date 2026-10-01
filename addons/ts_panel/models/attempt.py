from odoo import models


class TsAttempt(models.Model):
    _inherit = 'ts.attempt'

    def action_submit(self, *args, **kwargs):
        """Panel v2 (G28): ts_talent's matrix branch of action_submit never calls super(), so the
        usage event written in ts_org is skipped for TALENT-INV-15. This override sits above both and
        records the event for every finished panel attempt. Idempotent: one event per attempt."""
        res = super().action_submit(*args, **kwargs)
        if res:
            self._ts_panel_record_usage()
        return res

    def _ts_panel_record_usage(self):
        Usage = self.env['ts.usage.event'].sudo()
        for at in self.sudo():
            if at.state != 'done' or not at.workspace_id or at.source == 'import':
                continue
            if Usage.search_count([('attempt_id', '=', at.id)]):
                continue
            a = self.env['ts.assignment'].sudo().search([('attempt_id', '=', at.id)], limit=1)
            Usage.create({'workspace_id': at.workspace_id.id, 'attempt_id': at.id,
                          'assignment_id': a.id or False})
