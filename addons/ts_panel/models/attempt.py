from odoo import api, fields, models


class TsAttempt(models.Model):
    _inherit = 'ts.attempt'

    client_id = fields.Many2one('ts.panel.client', 'مراجع', index=True, ondelete='restrict')
    responsible_id = fields.Many2one(related='client_id.responsible_id', store=True, readonly=False,
                                     string='کارشناس مسئول', index=True)

    @api.model_create_multi
    def create(self, vals_list):
        """An imported result gets (or joins) the client of its historical person: contact data is never copied."""
        Client = self.env['ts.panel.client'].sudo()
        for vals in vals_list:
            if vals.get('source') == 'import' and vals.get('workspace_id') and vals.get('person_id') \
                    and not vals.get('client_id'):
                vals['client_id'] = Client.ts_for_import(vals['workspace_id'], self.env['res.partner'].browse(vals['person_id'])).id
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if 'state' in vals:
            self.sudo().client_id.ts_touch()
        return res

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
