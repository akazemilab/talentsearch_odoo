from odoo import api, fields, models, _
from odoo.exceptions import UserError

APPROVAL = [('Rejected', 'Rejected'), ('PendingReview', 'Pending review'), ('Approved', 'Approved')]


class KavenegarTemplate(models.Model):
    _name = 'kavenegar.template'
    _description = 'Kavenegar Verify (Lookup) template'
    _order = 'name'

    name = fields.Char('Template name', required=True, help='English letters/digits only, no spaces or underscore')
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    remote_id = fields.Char('Kavenegar template id', readonly=True, copy=False)
    approval = fields.Selection(APPROVAL, readonly=True, copy=False)
    text_message = fields.Text('SMS text', help='Use %token, %token2, %token3, %token10, %token20')
    voice_message = fields.Text('Voice text')
    source_type = fields.Selection([('0', 'Website'), ('1', 'App')], default='0', required=True)
    send_method = fields.Selection([('1', 'SMS'), ('2', 'Voice')], default='1', required=True)
    fallback_method = fields.Selection([('0', 'System default'), ('1', 'SMS'), ('2', 'Voice'), ('3', 'Disabled')],
                                       default='0', required=True)
    primary_line = fields.Char()
    secondary_line = fields.Char()
    switch_ttl = fields.Integer('Switch TTL (1-5)', default=3)
    source_url = fields.Char('Site / app URL')
    source_name = fields.Char('Site / app name')
    last_sync = fields.Datetime(readonly=True)
    note = fields.Char(readonly=True)

    _name_uniq = models.Constraint('unique(company_id, name)', 'Template names must be unique.')

    def _kv_payload(self):
        self.ensure_one()
        return {
            'name': self.name, 'textMessage': self.text_message, 'voiceMessage': self.voice_message,
            'sourceType': self.source_type, 'sendMethod': self.send_method,
            'fallBackMethod': self.fallback_method, 'primaryLineNumber': self.primary_line,
            'secondaryLineNumber': self.secondary_line, 'switchTTL': self.switch_ttl or None,
            'sourceUrl': self.source_url, 'sourceName': self.source_name,
        }

    def _kv_apply_remote(self, e):
        self.ensure_one()
        vals = {'last_sync': fields.Datetime.now()}
        if e.get('id') or e.get('templateId'):
            vals['remote_id'] = str(e.get('id') or e.get('templateId'))
        st = e.get('approvalStatus')
        if st in dict(APPROVAL):
            vals['approval'] = st
        for k, f in (('textMessage', 'text_message'), ('voiceMessage', 'voice_message')):
            if e.get(k) is not None:
                vals[f] = e[k]
        self.write(vals)

    def action_push(self):
        """Create (or update) the template on Kavenegar; it then waits for review."""
        for t in self:
            cl = t.company_id._kv_client()
            fn = (lambda: cl.template_update(t.remote_id, **t._kv_payload())) if t.remote_id \
                else (lambda: cl.template_add(**t._kv_payload()))
            res = t.company_id._kv_call(fn)
            t._kv_apply_remote(res[0] if res else {})
        return True

    def action_pull(self):
        for t in self.filtered('remote_id'):
            res = t.company_id._kv_call(t.company_id._kv_client().template_get, t.remote_id)
            if res:
                t._kv_apply_remote(res[0])
        return True

    def action_delete_remote(self):
        for t in self.filtered('remote_id'):
            t.company_id._kv_call(t.company_id._kv_client().template_delete, t.remote_id)
            t.write({'remote_id': False, 'approval': False})
        return True

    def action_clone(self):
        self.ensure_one()
        if not self.remote_id:
            raise UserError(_('Push the template to Kavenegar first.'))
        new = self.copy({'name': self.name + 'copy'})
        res = self.company_id._kv_call(self.company_id._kv_client().template_clone, new.name, source_id=self.remote_id)
        new._kv_apply_remote(res[0] if res else {})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': new.id, 'view_mode': 'form'}

    @api.model
    def action_sync_all(self):
        """Mirror every remote template (templatelist is paged)."""
        company = self.env.company
        cl = company._kv_client()
        page, seen = 1, 0
        while page <= 50:
            rows = company._kv_call(cl.template_list, page)
            if not rows:
                break
            for e in rows:
                rid = str(e.get('id') or e.get('templateId') or '')
                name = e.get('name')
                if not name:
                    continue
                t = self.search([('company_id', '=', company.id), '|', ('remote_id', '=', rid), ('name', '=', name)], limit=1)
                if not t:
                    t = self.create({'name': name, 'company_id': company.id})
                t._kv_apply_remote(e)
                seen += 1
            page += 1
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': _('%s templates synchronised', seen), 'type': 'success'}}
