from odoo import api, fields, models
from odoo.exceptions import ValidationError

MAX_VIEWS = 10


class TsSavedView(models.Model):
    """A member's saved list setup (04_data_model.md 3.8). The query holds only validated filter and sort
    parameters: search text can be a person's name and is never stored here."""
    _name = 'ts.saved.view'
    _description = 'Talent Search saved list view'
    _order = 'name, id'

    member_id = fields.Many2one('ts.workspace.member', required=True, index=True, ondelete='cascade')
    page = fields.Selection([('clients', 'شرکت‌کنندگان'), ('invites', 'دعوت‌ها'), ('audit', 'گزارش رویدادها')],
                            required=True, default='clients')
    name = fields.Char(required=True)
    query = fields.Char()
    is_default = fields.Boolean()
    columns = fields.Char()

    _member_name_uniq = models.UniqueIndex('(member_id, page, name)')

    @api.constrains('name')
    def _check_name(self):
        for v in self:
            if not (v.name or '').strip() or len(v.name) > 40:
                raise ValidationError('نام نما باید بین ۱ تا ۴۰ نویسه باشد.')

    @api.model_create_multi
    def create(self, vals_list):
        for v in vals_list:
            if 'name' in v:
                v['name'] = (v['name'] or '').strip()[:40]
            n = self.sudo().search_count([('member_id', '=', v.get('member_id')), ('page', '=', v.get('page', 'clients'))])
            if n >= MAX_VIEWS:
                raise ValidationError('حداکثر ۱۰ نمای ذخیره‌شده برای هر صفحه ممکن است.')
        recs = super().create(vals_list)
        for r in recs.filtered('is_default'):
            r._one_default()
        return recs

    def write(self, vals):
        res = super().write(vals)
        if vals.get('is_default'):
            self._one_default()
        return res

    def _one_default(self):
        self.ensure_one()
        self.sudo().search([('member_id', '=', self.member_id.id), ('page', '=', self.page),
                            ('id', '!=', self.id), ('is_default', '=', True)]).write({'is_default': False})
