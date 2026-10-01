from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .text import norm_text

KINDS = [('class', 'کلاس'), ('team', 'گروه'), ('tag', 'برچسب')]


class TsPanelGroup(models.Model):
    """A class, team or tag of the panel (04_data_model.md 3.2)."""
    _name = 'ts.panel.group'
    _description = 'Talent Search panel group'
    _order = 'name_norm, id'

    workspace_id = fields.Many2one('ts.workspace', required=True, index=True, ondelete='restrict')
    name = fields.Char('نام', required=True)
    name_norm = fields.Char(compute='_compute_name_norm', store=True, index=True)
    kind = fields.Selection(KINDS, 'نوع', default='class', required=True)
    active = fields.Boolean(default=True)
    client_ids = fields.Many2many('ts.panel.client', 'ts_panel_client_group_rel', 'group_id', 'client_id')
    client_count = fields.Integer(compute='_compute_client_count', store=True)

    _name_uniq = models.UniqueIndex('(workspace_id, name_norm) WHERE active IS TRUE')

    @api.depends('name')
    def _compute_name_norm(self):
        for g in self:
            g.name_norm = norm_text(g.name)

    @api.depends('client_ids')
    def _compute_client_count(self):
        for g in self:
            g.client_count = len(g.client_ids)

    @api.constrains('name')
    def _check_name(self):
        for g in self:
            if not (g.name or '').strip() or len(g.name) > 60:
                raise ValidationError('نام گروه باید بین ۱ تا ۶۰ نویسه باشد.')

    @api.model_create_multi
    def create(self, vals_list):
        for v in vals_list:
            if 'name' in v:
                v['name'] = (v['name'] or '').strip()[:60]
        return super().create(vals_list)

    def write(self, vals):
        if 'name' in vals:
            vals = dict(vals, name=(vals['name'] or '').strip()[:60])
        return super().write(vals)
