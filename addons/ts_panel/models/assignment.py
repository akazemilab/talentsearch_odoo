from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.ts_org.models.panel import norm_phone


class TsAssignment(models.Model):
    _inherit = 'ts.assignment'

    client_id = fields.Many2one('ts.panel.client', 'مراجع', index=True, ondelete='restrict')
    # The client is the single place where responsibility is set (04_data_model.md 2.4). Writing this field
    # writes the client, so every older writer (old page, member leaving, accept) keeps working.
    responsible_id = fields.Many2one(related='client_id.responsible_id', store=True, readonly=False,
                                     string='کارشناس مسئول', index=True)

    @api.model_create_multi
    def create(self, vals_list):
        Client = self.env['ts.panel.client'].sudo()
        for vals in vals_list:
            if not vals.get('client_id') and vals.get('workspace_id'):
                vals['client_id'] = Client.ts_for_invitation(vals).id
            c = Client.browse(vals.get('client_id'))
            if c and c.contact_locked:
                raise UserError('این فرد از دادهٔ تاریخی است و دعوت برای او فعلاً ممکن نیست.')
        recs = super().create(vals_list)
        recs.client_id.ts_touch()
        return recs

    def write(self, vals):
        res = super().write(vals)
        if vals.get('attempt_id'):
            for a in self.sudo():
                if a.client_id and not a.attempt_id.client_id:
                    a.attempt_id.client_id = a.client_id.id
        if vals.get('invitee_phone'):
            phone = norm_phone(vals['invitee_phone'])
            for c in self.sudo().client_id:
                if phone and not c.phone and not c.contact_locked:
                    c.phone = phone
        if set(vals) & {'user_id', 'attempt_id', 'withdrawn', 'declined', 'share_level'}:
            self.client_id.ts_touch()
        return res

    def action_accept(self, user, share):
        """Linking rule 1: the account is the key. Accepting links the account to the client."""
        self.ensure_one()
        client = self.client_id.sudo()
        if client.user_id and client.user_id != user:
            raise UserError('این دعوت قبلاً با حساب دیگری پذیرفته شده است.')
        attempt = super().action_accept(user, share)
        client = self.client_id.sudo()
        if client and not client.user_id:
            other = self.env['ts.panel.client'].sudo().search(
                [('workspace_id', '=', self.workspace_id.id), ('user_id', '=', user.id), ('id', '!=', client.id)], limit=1)
            if other:
                self.sudo().write({'client_id': other.id})
                if attempt.sudo().client_id == client:
                    attempt.sudo().client_id = other.id
                if not client.assignment_ids and not client.attempt_ids:
                    client.write({'state': 'archived', 'archived_on': fields.Datetime.now(), 'merged_into_id': other.id,
                                  'responsible_id': False})
                self.env['ts.audit.event'].log('client.auto_link', other, workspace=self.workspace_id)
                client = other
            else:
                client.user_id = user.id
        if client.responsible_id.user_id == user:
            client.responsible_id = False
        client.ts_touch()
        return attempt
