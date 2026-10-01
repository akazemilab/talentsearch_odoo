from datetime import timedelta
from odoo import fields
m = env.ref('ts_org.menu_ts_org_assignments')
print('GROUPS', [g.get_external_id() for g in m.group_ids], m.parent_id.group_ids.mapped('name'))
DR = env['ts.data.request']
print('DOM', DR._search_overdue('=', True), DR._search_overdue('=', False))
u = env['res.users'].search([], limit=1)
r = DR.sudo().create({'user_id': u.id, 'kind': 'export', 'due_on': fields.Date.today() - timedelta(days=1)})
print('OV', r.overdue, DR.sudo().search([('overdue', '=', True)]).ids, r.id)
env.cr.rollback()
