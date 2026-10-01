from odoo import api, fields, models


class TsAttempt(models.Model):
    _inherit = 'ts.attempt'

    client_id = fields.Many2one('ts.panel.client', 'مراجع', index=True, ondelete='restrict')
    responsible_id = fields.Many2one(related='client_id.responsible_id', readonly=False, string='کارشناس مسئول')

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
        if vals.keys() & {'source', 'person_id', 'workspace_id'}:
            Client = self.env['ts.panel.client'].sudo()
            for at in self.sudo().filtered(lambda r: r.source == 'import' and r.person_id and r.workspace_id and not r.client_id):
                at.client_id = Client.ts_for_import(at.workspace_id.id, at.person_id).id
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
            if not Usage.search_count([('attempt_id', '=', at.id)]):
                a = self.env['ts.assignment'].sudo().search([('attempt_id', '=', at.id)], limit=1)
                Usage.create({'workspace_id': at.workspace_id.id, 'attempt_id': at.id,
                              'assignment_id': a.id or False})
            self.env['ts.wallet']._for_workspace(at.workspace_id)._debit_usage(at)      # S11: one ledger row per attempt, idempotent

    def ts_org_assignment(self):
        """With up to `ts_panel.share_max_panels` shares per result (D3) the block on the report shows an active one first."""
        self.ensure_one()
        rows = self.env['ts.assignment'].sudo().search([('attempt_id', '=', self.id), ('user_id', '=', self.user_id.id)], order='id')
        active = rows.filtered(lambda a: a.share_level != 'none')
        return (active or rows)[:1]

    def ts_shares(self):
        """All panels this result is, or was, shared with / invited from: the participant's 'who can see' list."""
        self.ensure_one()
        return self.env['ts.assignment'].sudo().search([('attempt_id', '=', self.id), ('user_id', '=', self.user_id.id)], order='id')
