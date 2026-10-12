from odoo import api, models

from odoo.addons.ts_battery.models.battery import est_minutes


class TsBatteryTask(models.Model):
    _inherit = 'ts.battery'

    @api.depends('line_ids.instrument_id.current_version_id.active_item_count', 'line_ids.instrument_id.duration_minutes')
    def _compute_counts(self):
        super()._compute_counts()
        for b in self:
            tasks = b.line_ids.mapped('instrument_id').filtered(lambda i: i.current_version_id.mode == 'task')
            if tasks:
                b.est_minutes = est_minutes(b.item_count) + sum(tasks.mapped('duration_minutes'))
